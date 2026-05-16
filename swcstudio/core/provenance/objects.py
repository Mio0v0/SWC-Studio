"""Content-addressed, zstd-compressed blob store.

Implements PROVENANCE_SPEC §1 (``objects/`` directory) and the storage
contract referenced from §4 (every diff/snapshot/AI-run/env blob lives
here, named by the SHA-256 of its uncompressed contents).

Layout::

    .history/objects/
        ab/abc123...zst        # compressed blob; sha256 of raw content
        cd/cde456...zst
        ...

Why this shape:

* **Content addressing.** A blob's filename equals the SHA-256 hex of
  its uncompressed bytes, so two writers producing the same content
  cannot collide and natural deduplication is free (an env captured
  twice is stored once).
* **2-char prefix subdirs.** Same convention git uses for loose
  objects. Caps any single directory at ~256 entries even for stores
  with millions of blobs, keeping ``readdir`` cheap on every OS.
* **Atomic writes.** New blobs land via "write to temp file in the
  same dir, fsync, then ``os.replace`` onto the final name". A crash
  mid-write leaves a stray ``.tmp.*`` file but never a half-written
  blob with the wrong content under a real SHA.
* **Immutability.** Existing blobs are never rewritten. ``put()`` is a
  no-op if the SHA already exists, which lets callers blindly re-store
  identical content (very common — same env, same diff for repeated
  no-op ops, etc.).

Compression: zstd level 3 by default (per spec "open items deferred to
implementation"). Tunable via ``ObjectStore(compression_level=...)``.
"""

from __future__ import annotations

import os
import secrets
import tempfile
from pathlib import Path
from typing import Iterator

import zstandard as zstd

from swcstudio.core.provenance.canonical import sha256_hex

__all__ = ["ObjectStore", "BlobNotFoundError", "BlobCorruptError"]


# Default zstd level. Level 3 is the standard "fast and good enough"
# choice; we revisit after measuring real workloads (spec §"open items").
_DEFAULT_LEVEL = 3


class BlobNotFoundError(KeyError):
    """Raised by :meth:`ObjectStore.get` when no blob exists for the SHA."""


class BlobCorruptError(RuntimeError):
    """Raised when a blob's decompressed content does not hash to its filename.

    Indicates either on-disk corruption (bit rot, partial write that
    somehow escaped the atomic-rename guard) or tampering. ``verify``
    detects it; ``get`` does **not** validate by default to keep reads
    fast.
    """


class ObjectStore:
    """Content-addressed blob store rooted at ``.history/objects/``.

    Thread-safety: a single ``ObjectStore`` instance is safe to use
    from multiple threads in the same process. Cross-process safety
    is the caller's responsibility — that's what ``lockfile.LockFile``
    around the whole ``.history/`` directory is for.
    """

    def __init__(self, root: str | os.PathLike[str], *, compression_level: int = _DEFAULT_LEVEL) -> None:
        self._root = Path(root)
        self._level = compression_level
        # We don't ``mkdir`` eagerly; the first ``put()`` creates the
        # tree. This keeps ObjectStore() side-effect-free, which makes
        # tests and dry-run callers cheap.

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------------------
    # writing
    # ------------------------------------------------------------------

    def put(self, data: bytes) -> str:
        """Store ``data`` and return its SHA-256 hex.

        Idempotent: if a blob with the resulting SHA already exists,
        no I/O is performed beyond the existence check.
        """
        sha = sha256_hex(data)
        target = self._path_for(sha)
        if target.exists():
            return sha

        target.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write. We compress into a temp file in the same
        # directory (so the final ``os.replace`` is a same-filesystem
        # rename, which POSIX guarantees atomic), fsync the file, then
        # rename onto the canonical name.
        compressor = zstd.ZstdCompressor(level=self._level)
        compressed = compressor.compress(data)

        # Random-suffix temp name avoids two concurrent ``put()`` calls
        # for the same SHA stomping each other's temp files (still
        # safe because the final rename is atomic and idempotent, but
        # we want to avoid one writer deleting another's in-flight
        # temp file).
        tmp_name = f".tmp.{sha[:8]}.{secrets.token_hex(4)}"
        tmp_path = target.parent / tmp_name
        try:
            with open(tmp_path, "wb") as fh:
                fh.write(compressed)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, target)
        except BaseException:
            # Best-effort cleanup. ``os.replace`` already moved the
            # file on success, so unlinking the temp here only fires
            # on failure paths.
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
            raise

        return sha

    # ------------------------------------------------------------------
    # reading
    # ------------------------------------------------------------------

    def get(self, sha: str) -> bytes:
        """Return the uncompressed bytes for blob ``sha``.

        Does **not** verify the hash on read; that would double the
        cost of every ``get`` for protection against an extremely rare
        failure. Use :meth:`verify` for explicit integrity checks.
        """
        path = self._path_for(sha)
        if not path.exists():
            raise BlobNotFoundError(sha)
        with open(path, "rb") as fh:
            compressed = fh.read()
        return zstd.ZstdDecompressor().decompress(compressed)

    def exists(self, sha: str) -> bool:
        return self._path_for(sha).exists()

    def iter_shas(self) -> Iterator[str]:
        """Yield every stored SHA. Order is unspecified.

        Used by :meth:`verify` and by garbage collection
        (``swcstudio history gc``).
        """
        if not self._root.exists():
            return
        for prefix_dir in self._root.iterdir():
            if not prefix_dir.is_dir() or len(prefix_dir.name) != 2:
                continue
            for blob in prefix_dir.iterdir():
                if blob.suffix != ".zst" or blob.name.startswith(".tmp."):
                    continue
                yield blob.stem  # filename without ".zst"

    # ------------------------------------------------------------------
    # integrity + maintenance
    # ------------------------------------------------------------------

    def verify(self, sha: str) -> None:
        """Decompress blob ``sha`` and confirm it hashes back to ``sha``.

        Raises :class:`BlobNotFoundError` if the blob is missing, or
        :class:`BlobCorruptError` if either decompression fails (raw
        bit-rot inside the .zst frame) or the decompressed bytes hash
        to a different SHA than the filename.
        """
        if not self.exists(sha):
            raise BlobNotFoundError(sha)
        try:
            data = self.get(sha)
        except zstd.ZstdError as e:
            raise BlobCorruptError(
                f"blob {sha} failed to decompress: {e}"
            ) from e
        actual = sha256_hex(data)
        if actual != sha:
            raise BlobCorruptError(
                f"blob {sha} decompresses to content with sha {actual}"
            )

    def remove(self, sha: str) -> None:
        """Remove blob ``sha`` if present. No error if absent.

        Only the GC verb should call this; production code paths must
        treat the store as append-only.
        """
        path = self._path_for(sha)
        try:
            path.unlink()
        except FileNotFoundError:
            return
        # Best-effort prune of an empty 2-char prefix dir. Failing is
        # harmless — we just leave an empty dir for a future GC pass.
        try:
            path.parent.rmdir()
        except OSError:
            pass

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _path_for(self, sha: str) -> Path:
        if len(sha) != 64 or not all(c in "0123456789abcdef" for c in sha):
            raise ValueError(f"not a sha256 hex string: {sha!r}")
        return self._root / sha[:2] / f"{sha}.zst"
