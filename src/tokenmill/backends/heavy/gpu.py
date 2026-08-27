"""What accelerator this machine has, answered without importing PyTorch.

``tokenmill doctor`` exists to stop somebody spending an hour installing Marker
on hardware that cannot run it. That only works if the answer is **true**, and
the ways to get it wrong are specific:

* **"CUDA is installed" is not "there is a usable GPU".** A machine can have the
  CUDA toolkit, the driver libraries and ``nvidia-smi`` and still have no card —
  a container without ``--gpus``, a driver/library version mismatch, a
  passed-through device that failed to initialise. ``nvidia-smi`` then runs and
  reports no devices, or fails with a driver error. Both are reported as *CUDA
  present, no usable device*, which is a different sentence from *no GPU*
  because it needs a different fix.
* **Apple Silicon is not CUDA.** Marker and Surya run on MPS; MinerU's and
  olmOCR's vLLM paths do not. Saying "GPU: yes" on a Mac would send somebody
  down the wrong install.
* **We cannot ask PyTorch.** Importing torch into the tokenmill process is
  exactly what ``CONTRIBUTING.md`` rule 1 forbids, and torch is not installed
  anyway. So this reads the driver's own tooling and says what it found rather
  than what a framework would report.

**Nothing here is inferred from the platform alone.** ``sys.platform ==
"darwin"`` and an ``arm64`` machine really does mean a Metal-capable GPU exists
— that is a fact about the hardware, not a guess — but whether any *given*
PyTorch build can use it is a fact about that build, and this says so instead of
answering for it.

The one thing this module deliberately does **not** do is report a GPU by
running a heavy backend's own detection. That would mean importing torch inside
a virtual environment we do not control, on a command a user expects to be
instant. :func:`describe_environment_torch` is the opt-in version, used by
``doctor`` only when a backend environment already exists, and it is time-boxed.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from tokenmill.backends._subprocess import find_tool, run_tool
from tokenmill.core.errors import ConversionError

__all__ = [
    "Accelerator",
    "GpuDevice",
    "GpuReport",
    "describe_environment_torch",
    "detect_gpu",
]

#: How long any probe here may take. Short: ``doctor`` is a command someone runs
#: while deciding what to install, and a hung driver query is worse than an
#: unknown answer.
_PROBE_TIMEOUT_S: Final = 8.0

#: Where a CUDA toolkit is usually unpacked, checked only to tell "no NVIDIA
#: anything" apart from "NVIDIA software present, no working card".
_CUDA_MARKERS: Final[tuple[str, ...]] = (
    "/usr/local/cuda",
    "/usr/lib/x86_64-linux-gnu/libcuda.so.1",
    "/usr/lib64/libcuda.so.1",
)


class Accelerator(StrEnum):
    """What kind of accelerator was found."""

    #: No accelerator, and no vendor software either.
    NONE = "none"
    #: A working NVIDIA card.
    CUDA = "cuda"
    #: NVIDIA software is installed and no usable device answered.
    CUDA_UNUSABLE = "cuda-unusable"
    #: A working AMD card through ROCm.
    ROCM = "rocm"
    #: Apple Silicon; Metal is available to frameworks that support it.
    APPLE = "apple"


@dataclass(frozen=True, slots=True)
class GpuDevice:
    """One accelerator this machine has.

    Attributes:
        name: The device's own name, as its driver reports it.
        memory_mb: Total memory in megabytes, or ``None`` when the driver did
            not say. **Never estimated** — a wrong VRAM figure is exactly the
            number that makes somebody install a model that will not fit.
    """

    name: str
    memory_mb: int | None

    def describe(self) -> str:
        """Render the device for a report.

        Returns:
            The name, with its memory when that is known.
        """
        if self.memory_mb is None:
            return f"{self.name} (memory not reported)"
        return f"{self.name} ({self.memory_mb / 1024:.1f} GiB)"


@dataclass(frozen=True, slots=True)
class GpuReport:
    """What was found, and what it means for the heavy backends.

    Attributes:
        accelerator: The kind found.
        devices: Every device the driver listed.
        driver: The driver version, when one was reported.
        detail: One sentence a user can act on.
        notes: Anything qualifying the answer — a driver error, an
            unverifiable framework claim.
    """

    accelerator: Accelerator
    devices: tuple[GpuDevice, ...] = ()
    driver: str | None = None
    detail: str = ""
    notes: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        """Whether a heavy backend could actually run on this machine.

        Returns:
            True for a working CUDA or ROCm card, and for Apple Silicon.
            ``CUDA_UNUSABLE`` is False on purpose: software without a device is
            the case this whole module exists to distinguish.
        """
        return self.accelerator in {Accelerator.CUDA, Accelerator.ROCM, Accelerator.APPLE}

    @property
    def total_memory_mb(self) -> int | None:
        """Total memory across every device that reported some.

        Returns:
            The sum, or ``None`` when no device reported any.
        """
        known = [d.memory_mb for d in self.devices if d.memory_mb is not None]
        return sum(known) if known else None


def detect_gpu() -> GpuReport:
    """Report what accelerator this machine has.

    Never raises: every probe is a subprocess that may be absent, may fail, or
    may hang, and a diagnostic command that crashes is worse than one that says
    it does not know.

    Returns:
        The report.
    """
    nvidia = _probe_nvidia()
    if nvidia is not None:
        return nvidia

    rocm = _probe_rocm()
    if rocm is not None:
        return rocm

    if sys.platform == "darwin" and platform.machine() == "arm64":
        return GpuReport(
            accelerator=Accelerator.APPLE,
            devices=(GpuDevice(name=f"Apple Silicon ({platform.machine()})", memory_mb=None),),
            detail=(
                "Apple Silicon. Metal is available to frameworks that support it: "
                "Marker and Surya run on MPS, and are slower than on a comparable "
                "NVIDIA card"
            ),
            notes=(
                "Memory is shared with the system, so there is no separate VRAM figure to report.",
                "vLLM has no MPS backend, so MinerU's and olmOCR's vLLM paths and "
                "the DeepSeek-OCR and dots.ocr services do not run here.",
            ),
        )

    if any(Path(marker).exists() for marker in _CUDA_MARKERS):
        return GpuReport(
            accelerator=Accelerator.CUDA_UNUSABLE,
            detail=(
                "NVIDIA software is installed but no usable device answered. "
                "This is what a container started without --gpus looks like, and "
                "also what a driver/library version mismatch looks like"
            ),
            notes=("`nvidia-smi` was absent or reported no devices.",),
        )

    return GpuReport(
        accelerator=Accelerator.NONE,
        detail="No GPU found. Every heavy backend will be unavailable",
    )


def _probe_nvidia() -> GpuReport | None:
    """Ask ``nvidia-smi`` what cards there are.

    Returns:
        The report, or ``None`` when ``nvidia-smi`` is not installed at all —
        which the caller treats as "look somewhere else" rather than as "no
        GPU", because a machine can have a card and a broken driver package.
    """
    binary = find_tool("nvidia-smi")
    if binary is None:
        return None

    try:
        result = run_tool(
            [
                binary,
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            backend_id="doctor",
            timeout_s=_PROBE_TIMEOUT_S,
            expect_success=False,
        )
    except (ConversionError, OSError) as exc:
        return GpuReport(
            accelerator=Accelerator.CUDA_UNUSABLE,
            detail="nvidia-smi is installed but could not be run",
            notes=(str(exc)[:200],),
        )

    devices: list[GpuDevice] = []
    driver: str | None = None
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2 or not parts[0]:
            continue
        devices.append(GpuDevice(name=parts[0], memory_mb=_as_int(parts[1])))
        if len(parts) > 2 and parts[2]:
            driver = parts[2]

    if not devices:
        # The important case, and the reason this module exists. `nvidia-smi`
        # ran, so the software is there; it listed nothing, so there is no card
        # this process can use. Saying "no GPU" would send the user to buy one;
        # saying "GPU present" would send them to install a 5 GB model.
        message = result.stderr.strip() or result.stdout.strip()
        return GpuReport(
            accelerator=Accelerator.CUDA_UNUSABLE,
            detail=(
                "nvidia-smi ran and reported no usable device. The NVIDIA "
                "software is installed; nothing is available to compute on"
            ),
            notes=(message[:300],) if message else (),
        )

    return GpuReport(
        accelerator=Accelerator.CUDA,
        devices=tuple(devices),
        driver=driver,
        detail=f"{len(devices)} NVIDIA device(s) available",
    )


def _probe_rocm() -> GpuReport | None:
    """Ask ``rocm-smi`` what AMD cards there are.

    Deliberately shallower than the NVIDIA probe: ``rocm-smi``'s output format
    has changed between releases and parsing it for a VRAM figure would be
    guessing. Presence and device count are reported; memory is left ``None``
    rather than estimated.

    Returns:
        The report, or ``None`` when ``rocm-smi`` is not installed.
    """
    binary = find_tool("rocm-smi")
    if binary is None:
        return None

    try:
        result = run_tool(
            [binary, "--showproductname"],
            backend_id="doctor",
            timeout_s=_PROBE_TIMEOUT_S,
            expect_success=False,
        )
    except (ConversionError, OSError):
        return None

    names = [
        line.split(":", 1)[1].strip()
        for line in result.stdout.splitlines()
        if ":" in line and "card series" in line.lower()
    ]
    if not names:
        return None
    return GpuReport(
        accelerator=Accelerator.ROCM,
        devices=tuple(GpuDevice(name=name, memory_mb=None) for name in names),
        detail=f"{len(names)} AMD ROCm device(s) available",
        notes=(
            "VRAM is not reported: rocm-smi's output format has changed between "
            "releases and a parsed figure here would be a guess.",
            "Every heavy backend here is tested against CUDA by its authors. "
            "ROCm support varies by backend and by version.",
        ),
    )


def describe_environment_torch(interpreter: Path | str) -> str | None:
    """Ask one backend's own interpreter what PyTorch thinks of this machine.

    The authoritative answer, and the one this module cannot give: whether the
    *installed* PyTorch was built with CUDA, with ROCm, or for CPU only. A
    CPU-only wheel on a machine with a working card reports no GPU, and that is
    a real and common way to spend an hour confused.

    Never called unless a backend environment already exists, because it costs
    a PyTorch import — several seconds — and ``doctor`` should be instant on a
    machine with nothing installed.

    Args:
        interpreter: The Python that has the backend installed.

    Returns:
        One line describing what torch reports, or ``None`` when torch is
        absent or the probe failed. ``None`` means "not known", which the
        report prints as such rather than filling in.
    """
    script = (
        "import torch;"
        "cuda=torch.cuda.is_available();"
        "mps=getattr(torch.backends,'mps',None) is not None "
        "and torch.backends.mps.is_available();"
        "print(f'torch {torch.__version__}, cuda={cuda}, mps={mps}, "
        'built_for={torch.version.cuda or "cpu"}\')'
    )
    try:
        result = run_tool(
            [str(interpreter), "-c", script],
            backend_id="doctor",
            timeout_s=_PROBE_TIMEOUT_S * 4,
            expect_success=False,
        )
    except (ConversionError, OSError):
        return None
    line = result.stdout.strip().splitlines()
    return line[0] if line else None


def _as_int(value: str) -> int | None:
    """Parse a driver's numeric field without letting a surprise become a crash.

    Args:
        value: The raw field.

    Returns:
        The integer, or ``None`` when it is not one. ``nvidia-smi`` prints
        ``[N/A]`` for a device that will not answer, and a report that said
        "0 GiB" there would be a worse lie than saying nothing.
    """
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
