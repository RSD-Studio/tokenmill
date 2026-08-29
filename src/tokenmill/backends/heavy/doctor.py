"""What ``tokenmill doctor`` reports, gathered in one place.

The command exists for one purpose the plan states outright: *stop someone
spending an hour installing Marker on hardware that cannot run it.* Everything
here follows from that.

**It is a library function, not CLI code.** ``cli/main.py`` renders it and the
GUI could too; the gathering is here so both see the same facts and a test can
drive it without a terminal. That is the same rule the Phase 8 GUI is built on.

**It never guesses.** A fact it could not establish is reported as *not known*
rather than filled in with a plausible value: an invented VRAM figure is exactly
the number that makes somebody install a model that will not fit, and a
confident "no GPU" on a machine whose driver is merely misconfigured sends them
to buy hardware they already own.

**It is cheap by default.** No model is contacted, no torch is imported into
this process, and nothing that is not installed is probed. The one expensive
question — what the *installed* PyTorch thinks of this machine — is asked only
of environments that already exist, because that is the one place the answer can
differ from the driver's and be the answer that matters: a CPU-only torch wheel
on a machine with a working card reports no GPU, and that is a real and common
hour to lose.
"""

from __future__ import annotations

import platform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from tokenmill.backends.heavy.base import HeavyTier, interpreter_names
from tokenmill.backends.heavy.gpu import GpuReport, describe_environment_torch, detect_gpu
from tokenmill.core.models import Availability, IsolationMode, LicenseTier
from tokenmill.core.registry import Registry, default_registry

__all__ = ["BackendDiagnosis", "Diagnosis", "diagnose"]


@dataclass(frozen=True, slots=True)
class BackendDiagnosis:
    """What ``doctor`` found out about one backend.

    Attributes:
        backend_id: Its id.
        name: Its display name.
        availability: Whether it can run, and why not.
        licence: The licence of the wrapped tool's **code**.
        tier: What that licence permits.
        weights_licence: What the model weights are under, or ``None`` when
            that has not been verified. Separate from ``licence`` because they
            routinely differ, and the difference is where the surprises are.
        requires_gpu: Whether usable performance needs one.
        install_steps: The commands that would make it work.
        torch: What the backend's own PyTorch reports, when it has one.
        notes: Anything else worth saying about this backend on this machine.
    """

    backend_id: str
    name: str
    availability: Availability
    licence: str
    tier: LicenseTier
    weights_licence: str | None = None
    requires_gpu: bool = False
    install_steps: tuple[str, ...] = ()
    torch: str | None = None
    notes: tuple[str, ...] = ()

    @property
    def usable_here(self) -> bool:
        """Whether this backend could actually do work on this machine.

        Returns:
            True only when it is available. A GPU backend that is installed on a
            machine with no GPU is *available* — it will start, and fail or
            crawl — and :attr:`notes` says so. Conflating the two would make
            ``doctor`` less useful than ``backends``.
        """
        return bool(self.availability)


@dataclass(frozen=True, slots=True)
class Diagnosis:
    """Everything ``tokenmill doctor`` reports.

    Attributes:
        python: The running interpreter's version.
        platform_description: OS and architecture.
        gpu: What accelerator was found.
        backends: One entry per registered backend, id order.
        tools: External programs that were looked for, and where they were
            found.
        warnings: Things the user should know about this machine.
    """

    python: str
    platform_description: str
    gpu: GpuReport
    backends: tuple[BackendDiagnosis, ...] = ()
    tools: tuple[tuple[str, str | None], ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def heavy(self) -> tuple[BackendDiagnosis, ...]:
        """The GPU-tier backends only.

        Returns:
            Those that declare ``requires_gpu``.
        """
        return tuple(b for b in self.backends if b.requires_gpu)

    @property
    def available_count(self) -> int:
        """How many backends can run here.

        Returns:
            The count.
        """
        return sum(1 for b in self.backends if b.usable_here)


#: External programs worth reporting on, and why each matters. Not every binary
#: any backend might use — only the ones whose absence changes what tokenmill
#: can do, so the report stays readable.
_TOOLS: tuple[tuple[str, str], ...] = (
    ("pandoc", "the pandoc backend"),
    ("soffice", "the libreoffice backend"),
    ("node", "repomix, via npx"),
    ("npx", "repomix, without a local install"),
    ("code2prompt", "the code2prompt backend"),
    ("nvidia-smi", "NVIDIA GPU detection"),
    ("docker", "the heavy backends' compose files"),
)


def diagnose(registry: Registry | None = None, *, probe_torch: bool = True) -> Diagnosis:
    """Gather everything ``tokenmill doctor`` reports.

    Args:
        registry: Where backends come from; the process-wide one by default.
        probe_torch: Whether to ask each installed heavy backend's own
            interpreter what PyTorch reports. Costs a few seconds per installed
            environment and nothing at all when none exist, since it only runs
            for environments that are already there. Turned off in tests that
            do not want a subprocess.

    Returns:
        The diagnosis.
    """
    backends = registry if registry is not None else default_registry()
    gpu = detect_gpu()

    diagnoses: list[BackendDiagnosis] = []
    for converter in backends:
        info = converter.info
        heavy = converter if isinstance(converter, HeavyTier) else None
        torch = None
        notes: list[str] = []

        if heavy is not None:
            environment = heavy.local_environment
            if probe_torch and environment is not None and environment.is_dir():
                torch = _torch_in(environment)
            if info.requires_gpu and not gpu.usable:
                notes.append(
                    "this machine has no usable GPU, so it will be very slow or "
                    "will fail at model load"
                )
            if info.isolation is IsolationMode.SERVICE:
                notes.append(
                    "nothing to install locally: run the model yourself and pass "
                    f"--extra {info.id}_url=http://host:8000"
                )

        diagnoses.append(
            BackendDiagnosis(
                backend_id=info.id,
                name=info.name,
                availability=converter.is_available(),
                licence=info.license,
                tier=info.license_tier,
                weights_licence=heavy.weights_licence if heavy is not None else None,
                requires_gpu=info.requires_gpu,
                install_steps=heavy.install_steps if heavy is not None else (),
                torch=torch,
                notes=tuple(notes),
            )
        )

    return Diagnosis(
        python=f"{platform.python_version()} ({sys.executable})",
        platform_description=f"{platform.system()} {platform.release()} on {platform.machine()}",
        gpu=gpu,
        backends=tuple(sorted(diagnoses, key=lambda d: d.backend_id)),
        tools=tuple((name, shutil.which(name)) for name, _ in _TOOLS),
        warnings=tuple(_warnings_for(gpu)),
    )


def _torch_in(environment: Path) -> str | None:
    """Ask one backend environment's interpreter what PyTorch reports.

    Args:
        environment: The virtual environment's root.

    Returns:
        One line, or ``None`` when torch is absent or the probe failed.
    """
    for sub in interpreter_names():
        for name in ("python", "python.exe"):
            candidate = environment / sub / name
            if candidate.is_file():
                return describe_environment_torch(candidate)
    return None


def _warnings_for(gpu: GpuReport) -> list[str]:
    """Say what this machine's accelerator means for the heavy tier.

    Args:
        gpu: What was found.

    Returns:
        Zero or more sentences, each about a decision the user might otherwise
        get wrong.
    """
    notes = list(gpu.notes)
    if gpu.accelerator.value == "cuda-unusable":
        notes.append(
            "NVIDIA software is present and no device answered. Installing a "
            "heavy backend will succeed and then fail at model load. Check "
            "`nvidia-smi` directly, and whether this is a container started "
            "without --gpus."
        )
    elif not gpu.usable:
        notes.append(
            "No GPU. The heavy backends will install and will be too slow to "
            "use; the light tier (pdfplumber, markitdown, kreuzberg) and the "
            "external tier (pandoc, LibreOffice, PyMuPDF4LLM) are what this "
            "machine is for."
        )
    return notes
