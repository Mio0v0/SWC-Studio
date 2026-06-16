"""Best-effort GPU readiness diagnostics for SWC-Studio.

The bundled desktop executable is expected to run on CPU. Source and pip
installs can use CUDA when the active Python environment has a compatible
PyTorch / PyTorch Geometric stack and the NVIDIA driver exposes a CUDA
device. This module reports that state without making GPU support a hard
startup dependency.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import importlib
import platform
import shutil
import subprocess
import sys
from typing import Any


GPU_INSTALL_DOC = "docs/GPU_INSTALL.md"
PYTORCH_INSTALL_URL = "https://pytorch.org/get-started/locally/"
PYG_INSTALL_URL = "https://pytorch-geometric.readthedocs.io/en/2.6.1/install/installation.html"


@dataclass
class GPUStatus:
    """Structured GPU readiness report.

    ``ready`` means the current Python process can import torch,
    torch_geometric, and see at least one CUDA device through
    ``torch.cuda.is_available()``.
    """

    ready: bool
    status: str
    summary: str
    python_version: str
    platform: str
    torch_installed: bool = False
    torch_version: str | None = None
    torch_cuda_build: str | None = None
    torch_cuda_available: bool = False
    torch_device_count: int = 0
    torch_devices: list[str] = field(default_factory=list)
    torch_error: str | None = None
    torch_geometric_installed: bool = False
    torch_geometric_version: str | None = None
    torch_geometric_error: str | None = None
    nvidia_smi_available: bool = False
    nvidia_smi: str | None = None
    nvidia_smi_error: str | None = None
    missing: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    docs: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_gpu_readiness() -> GPUStatus:
    """Inspect the active environment and return a GPU readiness report."""

    missing: list[str] = []
    recommendations: list[str] = []
    torch_installed = False
    torch_version = None
    torch_cuda_build = None
    torch_cuda_available = False
    torch_device_count = 0
    torch_devices: list[str] = []
    torch_error = None

    try:
        torch = importlib.import_module("torch")
        torch_installed = True
        torch_version = str(getattr(torch, "__version__", "") or "")
        torch_cuda_build = getattr(getattr(torch, "version", None), "cuda", None)
        try:
            torch_cuda_available = bool(torch.cuda.is_available())
            torch_device_count = int(torch.cuda.device_count()) if torch_cuda_available else 0
            for idx in range(torch_device_count):
                try:
                    torch_devices.append(str(torch.cuda.get_device_name(idx)))
                except Exception:  # noqa: BLE001
                    torch_devices.append(f"CUDA device {idx}")
        except Exception as exc:  # noqa: BLE001
            torch_error = f"{exc.__class__.__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001
        torch_error = f"{exc.__class__.__name__}: {exc}"

    pyg_installed = False
    pyg_version = None
    pyg_error = None
    try:
        pyg = importlib.import_module("torch_geometric")
        pyg_installed = True
        pyg_version = str(getattr(pyg, "__version__", "") or "")
    except Exception as exc:  # noqa: BLE001
        pyg_error = f"{exc.__class__.__name__}: {exc}"

    nvidia_smi_available, nvidia_smi, nvidia_smi_error = _probe_nvidia_smi()

    if not torch_installed:
        missing.append("PyTorch")
        recommendations.append("Install PyTorch in the active pip/source environment.")
    elif torch_cuda_build is None:
        missing.append("CUDA-enabled PyTorch")
        recommendations.append("Install a CUDA-enabled PyTorch build that matches the NVIDIA driver.")
    elif not torch_cuda_available:
        missing.append("CUDA device visible to PyTorch")
        recommendations.append(
            "Check the NVIDIA driver, CUDA runtime compatibility, and whether this machine has a supported GPU."
        )

    if not pyg_installed:
        missing.append("PyTorch Geometric")
        recommendations.append("Install PyTorch Geometric for the same PyTorch/CUDA stack.")

    if torch_installed and torch_cuda_build and torch_cuda_available and pyg_installed:
        ready = True
        status = "gpu-ready"
        summary = "GPU mode is available in this Python environment."
    elif torch_installed and pyg_installed:
        ready = False
        status = "cpu-only"
        summary = "SWC-Studio can run, but this environment is currently CPU-only."
    else:
        ready = False
        status = "missing-dependencies"
        summary = "SWC-Studio GPU mode is not ready in this Python environment."

    return GPUStatus(
        ready=ready,
        status=status,
        summary=summary,
        python_version=sys.version.split()[0],
        platform=f"{platform.system()} {platform.release()} ({platform.machine()})",
        torch_installed=torch_installed,
        torch_version=torch_version,
        torch_cuda_build=torch_cuda_build,
        torch_cuda_available=torch_cuda_available,
        torch_device_count=torch_device_count,
        torch_devices=torch_devices,
        torch_error=torch_error,
        torch_geometric_installed=pyg_installed,
        torch_geometric_version=pyg_version,
        torch_geometric_error=pyg_error,
        nvidia_smi_available=nvidia_smi_available,
        nvidia_smi=nvidia_smi,
        nvidia_smi_error=nvidia_smi_error,
        missing=missing,
        recommendations=recommendations,
        docs={
            "local": GPU_INSTALL_DOC,
            "pytorch": PYTORCH_INSTALL_URL,
            "pyg": PYG_INSTALL_URL,
        },
    )


def format_gpu_readiness(status: GPUStatus | None = None) -> str:
    """Return a concise human-readable GPU readiness report."""

    st = status or check_gpu_readiness()
    lines = [
        st.summary,
        "",
        f"Status: {st.status}",
        f"Python: {st.python_version}",
        f"Platform: {st.platform}",
        "",
        "Environment:",
        f"- PyTorch: {_yes_no(st.torch_installed)}"
        + (f" ({st.torch_version})" if st.torch_version else ""),
        f"- PyTorch CUDA build: {st.torch_cuda_build or 'none / CPU build'}",
        f"- CUDA visible to PyTorch: {_yes_no(st.torch_cuda_available)}",
        f"- CUDA device count: {st.torch_device_count}",
    ]
    if st.torch_devices:
        lines.append(f"- CUDA devices: {', '.join(st.torch_devices)}")
    lines.extend(
        [
            f"- PyTorch Geometric: {_yes_no(st.torch_geometric_installed)}"
            + (f" ({st.torch_geometric_version})" if st.torch_geometric_version else ""),
            f"- nvidia-smi: {_yes_no(st.nvidia_smi_available)}"
            + (f" ({st.nvidia_smi})" if st.nvidia_smi else ""),
        ]
    )

    errors = [e for e in (st.torch_error, st.torch_geometric_error, st.nvidia_smi_error) if e]
    if errors:
        lines.extend(["", "Diagnostics:"])
        lines.extend(f"- {e}" for e in errors)

    if st.missing:
        lines.extend(["", "Missing for GPU mode:"])
        lines.extend(f"- {item}" for item in st.missing)

    if st.recommendations:
        lines.extend(["", "Recommended next steps:"])
        lines.extend(f"- {item}" for item in st.recommendations)

    lines.extend(
        [
            "",
            "Notes:",
            "- The one-click executable is intended to be the reliable CPU build.",
            "- GPU acceleration is supported for pip/source installs when the active Python environment has matching CUDA packages.",
            "",
            "Documentation:",
            f"- SWC-Studio GPU setup: {st.docs['local']}",
            f"- PyTorch installer selector: {st.docs['pytorch']}",
            f"- PyTorch Geometric install guide: {st.docs['pyg']}",
        ]
    )
    return "\n".join(lines)


def _probe_nvidia_smi() -> tuple[bool, str | None, str | None]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return False, None, "nvidia-smi not found on PATH"
    try:
        completed = subprocess.run(
            [
                exe,
                "--query-gpu=name,driver_version",
                "--format=csv,noheader",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3,
        )
    except Exception as exc:  # noqa: BLE001
        return False, None, f"nvidia-smi failed: {exc.__class__.__name__}: {exc}"
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return False, None, f"nvidia-smi failed: {detail or completed.returncode}"
    first = (completed.stdout or "").strip().splitlines()
    return True, first[0].strip() if first else "", None


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
