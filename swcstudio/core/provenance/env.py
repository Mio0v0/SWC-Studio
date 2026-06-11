"""Environment fingerprint for AI-run reproducibility.

Implements PROVENANCE_SPEC §4 ("Env fingerprint blob") and §9
("AI env capture: full importlib.metadata snapshot + system info").

What's captured:

* **system**: OS name + version, machine arch, Python interpreter
  version, CPU count, optional CUDA/GPU info (best-effort, no extra
  deps for detection — if torch is importable we ask it).
* **packages**: every installed distribution from
  ``importlib.metadata`` with its version. This is intentionally a
  full snapshot (not just AI-relevant packages) because transitive
  deps can affect numerical reproducibility in subtle ways.

Storage: the fingerprint dict is JSON-encoded with
:func:`canonical_json` so two captures of the *same* environment
produce byte-identical blobs and therefore the same SHA. That's the
dedup mechanism — fifty AI runs in the same env reference one env
blob.
"""

from __future__ import annotations

import os
import platform
import sys
from importlib.metadata import distributions
from typing import Any

from swcstudio.core.provenance.canonical import sha256_hex
from swcstudio.core.provenance.events import canonical_json

__all__ = [
    "ENV_SCHEMA_VERSION",
    "capture_env",
    "env_hash",
]


ENV_SCHEMA_VERSION = 1


def capture_env() -> dict[str, Any]:
    """Snapshot the current Python + system environment.

    Pure-stdlib for the system block. ``importlib.metadata`` for the
    package block. CUDA/GPU detection is opportunistic — if ``torch``
    can be imported without side effects, we ask it; otherwise the
    fields are ``None``.

    The returned dict is the **full payload** that will be JSON-
    serialized and stored as a blob. Keep it deterministic and free
    of timestamps so identical environments dedup.
    """
    return {
        "schema_version": ENV_SCHEMA_VERSION,
        "system": _system_info(),
        "packages": _packages(),
    }


def env_hash(env: dict[str, Any]) -> str:
    """Hash an env dict the same way ObjectStore would after canonical_json.

    Useful for callers that want to know whether the current env blob
    will dedupe against an existing one without actually writing.
    Returns the bare hex (no ``sha256:`` prefix), matching the
    ``objects/`` filename convention.
    """
    return sha256_hex(canonical_json(env))


# ----------------------------------------------------------------------
# internals
# ----------------------------------------------------------------------


def _system_info() -> dict[str, Any]:
    """Stdlib-only system-info block.

    We deliberately avoid hostname / username / absolute paths to keep
    the env blob privacy-clean by default (spec §20: ``export-crate``
    strips PII; the blob itself shouldn't carry any to begin with).
    """
    info: dict[str, Any] = {
        "os": platform.system(),
        "os_version": platform.release(),
        "python_version": platform.python_version(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "cuda_version": None,
        "gpu": None,
    }
    # Opportunistic GPU/CUDA capture without forcing the import.
    if "torch" in sys.modules:
        info["cuda_version"], info["gpu"] = _torch_gpu_info()
    return info


def _torch_gpu_info() -> tuple[str | None, str | None]:
    try:
        import torch  # type: ignore
    except Exception:
        return None, None
    cuda_version = getattr(torch.version, "cuda", None)  # type: ignore[attr-defined]
    gpu_name: str | None = None
    try:
        if torch.cuda.is_available() and torch.cuda.device_count() > 0:
            gpu_name = torch.cuda.get_device_name(0)
    except Exception:
        pass
    return cuda_version, gpu_name


def _packages() -> dict[str, str]:
    """Map of distribution name -> version.

    Sorted for determinism. ``canonical_json`` will sort again, but
    sorting here too keeps the in-memory dict iteration stable and
    makes debugging easier.
    """
    pkgs: dict[str, str] = {}
    for dist in distributions():
        # ``Name`` is the canonical PyPI-style name; ``version`` is
        # the installed version string. We don't include ``Location``
        # or any other site-specific metadata — paths leak PII and
        # don't affect reproducibility.
        try:
            name = dist.metadata["Name"]
            version = dist.version
        except Exception:
            continue
        if not name:
            continue
        pkgs[str(name)] = str(version or "")
    return dict(sorted(pkgs.items()))
