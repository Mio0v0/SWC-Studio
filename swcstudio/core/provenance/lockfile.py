"""Cross-platform advisory lock for the ``.history/`` directory.

Spec §10: every mutating verb (``tracked_op``, ``tracked_session``,
GC, reindex) must hold a single advisory lock for the duration of the
critical section. If acquisition fails, the verb exits with a clear
diagnostic naming the holding PID and start time — no silent retry.

We use OS-level *advisory* locks rather than presence-of-file:

* ``fcntl.flock`` on POSIX (Linux, macOS).
* ``msvcrt.locking`` on Windows.

Both are released automatically by the OS on process exit, so a
crashed writer never leaves the directory permanently locked. A
sidecar ``.history/lock`` text file records who/when for diagnostics
only — its mere existence is *not* the lock; the OS ``flock`` is.
"""

from __future__ import annotations

import errno
import os
import sys
import time
from pathlib import Path
from typing import IO

__all__ = ["LockFile", "LockHeldError"]


_IS_WINDOWS = sys.platform.startswith("win")


class LockHeldError(RuntimeError):
    """Raised when the lock is already held by another process."""


class LockFile:
    """Context manager holding an exclusive lock on ``.history/lock``.

    Usage::

        with LockFile(history_dir):
            # safe to mutate events.jsonl, refs/, objects/, index.sqlite

    Re-entrant within the same process is **not** supported. If the
    same process tries to acquire twice, the second attempt raises
    :class:`LockHeldError` (most platforms' advisory locks are
    process-wide, not thread-wide).
    """

    def __init__(self, history_dir: str | os.PathLike[str]) -> None:
        self._dir = Path(history_dir)
        self._path = self._dir / "lock"
        self._fh: IO[bytes] | None = None

    # ------------------------------------------------------------------
    # context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "LockFile":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    # ------------------------------------------------------------------
    # primary API
    # ------------------------------------------------------------------

    def acquire(self) -> None:
        """Acquire the lock. Raises :class:`LockHeldError` on conflict."""
        if self._fh is not None:
            raise LockHeldError("LockFile already acquired by this instance")

        self._dir.mkdir(parents=True, exist_ok=True)

        # We open with read+write+create so we can both write the
        # diagnostic header (PID, start time) and so the file exists
        # for the OS to lock against.
        fh = open(self._path, "a+b")
        try:
            self._platform_lock(fh)
        except BlockingIOError as e:
            fh.close()
            holder = self._read_holder_for_diagnostic()
            raise LockHeldError(
                f"history directory {self._dir} is locked"
                + (f" by {holder}" if holder else "")
                + " — another swcstudio process may be writing"
            ) from e
        except OSError as e:
            fh.close()
            # Some platforms surface contention as EAGAIN/EACCES
            # instead of BlockingIOError. Treat the same.
            if e.errno in (errno.EAGAIN, errno.EACCES):
                holder = self._read_holder_for_diagnostic()
                raise LockHeldError(
                    f"history directory {self._dir} is locked"
                    + (f" by {holder}" if holder else "")
                ) from e
            raise

        # Now that the lock is held, overwrite the diagnostic header
        # so a future contender sees who's currently holding it.
        try:
            fh.seek(0)
            fh.truncate(0)
            fh.write(self._diagnostic_payload())
            fh.flush()
            os.fsync(fh.fileno())
        except OSError:
            # Diagnostic write is best-effort; the lock itself is the
            # primary correctness guarantee.
            pass

        self._fh = fh

    def release(self) -> None:
        """Release the lock. Idempotent (no error if not held)."""
        if self._fh is None:
            return
        try:
            self._platform_unlock(self._fh)
        finally:
            try:
                self._fh.close()
            finally:
                self._fh = None

    # ------------------------------------------------------------------
    # platform-specific lock implementations
    # ------------------------------------------------------------------

    if _IS_WINDOWS:
        @staticmethod
        def _platform_lock(fh: IO[bytes]) -> None:
            import msvcrt
            # Lock 1 byte at offset 0 in non-blocking mode. Windows
            # locks bytes, not whole files; locking byte 0 with
            # LK_NBLCK is the conventional "whole-file lock".
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

        @staticmethod
        def _platform_unlock(fh: IO[bytes]) -> None:
            import msvcrt
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
    else:
        @staticmethod
        def _platform_lock(fh: IO[bytes]) -> None:
            import fcntl
            # Non-blocking exclusive lock. ``LOCK_NB`` makes us raise
            # immediately on conflict instead of blocking forever,
            # which is the contract spec §10 requires.
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        @staticmethod
        def _platform_unlock(fh: IO[bytes]) -> None:
            import fcntl
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # diagnostic payload (human-readable; not load-bearing)
    # ------------------------------------------------------------------

    def _diagnostic_payload(self) -> bytes:
        return (
            f"pid={os.getpid()} "
            f"acquired_at={time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n"
        ).encode("utf-8")

    def _read_holder_for_diagnostic(self) -> str | None:
        try:
            return self._path.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
