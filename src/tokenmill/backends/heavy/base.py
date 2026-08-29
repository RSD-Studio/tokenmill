"""What every heavy subprocess backend shares.

Each of Marker, MinerU, Surya and olmOCR is the same shape: a Python package
with a command-line entry point, installed into **an environment of its own**,
producing files in an output directory. The differences are the executable's
name, the arguments, and where the Markdown ends up. Everything else is here.

**Why a separate environment rather than an extra.** ``pyproject.toml``'s
``heavy = []`` group is empty and stays empty. These packages resolve to PyTorch
plus a CUDA stack — several gigabytes — and ``CONTRIBUTING.md`` rule 1 says the
core install stays light. They also disagree with each other and with docling
about transformers versions, so installing two of them into one environment is a
resolver problem waiting to happen. One environment each, and the install hint
says exactly that.

This is the pattern ``backends/external/pymupdf4llm_pdf.py`` established for an
AGPL package, reused here for a different reason. For PyMuPDF4LLM the separate
environment is a **licence** boundary — the package must not be importable from
here. For these it is a **dependency** boundary: two of the four are Apache-2.0
and could legally be imported; importing them would just put PyTorch in the
dependency tree. Same mechanism, different rule, and the distinction is kept
visible rather than blurred into "they are all isolated".

**Availability is answered without running anything expensive.** The probe looks
for the executable in the conventional environment, then on ``PATH``, and stops.
It does **not** import torch, check for a GPU, or contact a model host: a
``tokenmill backends`` listing must stay instant, and a user on a CPU-only
machine gets the same "here is how to install it" answer either way. Whether the
machine can *usefully* run it is what ``tokenmill doctor`` is for, and it says so
in a sentence rather than by making the backend disappear.

**Nothing here downloads a model.** Every one of these fetches weights from
``huggingface.co`` on first use, which is a multi-gigabyte network operation
inside a command the user may have believed was local. So a heavy backend
requires ``--allow-network`` on a run that has not already cached its models,
and refuses with :class:`~tokenmill.core.errors.NetworkRequired` otherwise —
the same rule the ``npx`` path in the repomix adapter follows, for the same
reason.
"""

from __future__ import annotations

import os
import sys
from abc import abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from tokenmill.backends.external.base import SubprocessConverter
from tokenmill.core.errors import BackendFailed, NetworkRequired
from tokenmill.core.models import Availability, ConvertOptions, Source
from tokenmill.core.protocol import ConversionContext

__all__ = [
    "HeavyConverter",
    "HeavyTier",
    "environment_root",
    "first_markdown",
    "interpreter_names",
]

#: Where a heavy backend's environment is expected to live, by convention.
#:
#: Under the user's data directory rather than beside the source tree: these are
#: multi-gigabyte installs that outlive any checkout, and a virtualenv inside a
#: repository is one ``rm -rf`` from being downloaded again.
_ENVIRONMENT_HOME: Final = Path.home() / ".local" / "share" / "tokenmill"

#: The ``--extra`` key pattern by which a user points an adapter at an
#: environment somewhere else entirely.
_EXTRA_TEMPLATE: Final = "{backend_id}_python"


def environment_root(name: str) -> Path:
    """Return the conventional environment directory for one heavy backend.

    Args:
        name: The backend's id.

    Returns:
        The directory the install instructions tell people to create.
    """
    return _ENVIRONMENT_HOME / name


def interpreter_names() -> tuple[str, ...]:
    """Return where an executable lives inside a virtual environment.

    Returns:
        The platform's relative directory names, POSIX first.
    """
    return ("Scripts",) if sys.platform == "win32" else ("bin",)


class HeavyTier:
    """What every GPU-tier backend declares, whichever way it is invoked.

    A marker **and** a small contract. The heavy tier has two shapes — a
    command in an environment of its own (Marker, Surya, MinerU, olmOCR) and a
    model served over HTTP (DeepSeek-OCR, dots.ocr) — which sit under different
    Phase 7 base classes and share no ancestor below :class:`object`.

    Without this, ``tokenmill doctor`` could only recognise one of them, which
    is not a hypothetical: the first version tested
    ``isinstance(converter, HeavyConverter)`` and silently gave the two service
    backends no install instructions, no weights-licence line and no
    "this machine has no GPU" note. Found by reading ``doctor``'s output rather
    than by a test, which is the Phase 8 lesson repeating itself.

    Attributes:
        install_steps: The exact commands that would make this work, shown when
            it is unavailable. Empty for a service backend, whose instruction is
            an address rather than an install.
        weights_licence: What the *model weights* are licensed under, as
            distinct from the code. ``None`` means **not verified**, which is
            the honest answer for every backend here: this sandbox cannot reach
            the host the weights live on. Kept separate from the code's licence
            because they routinely differ and the difference is where the
            surprises are.
    """

    install_steps: tuple[str, ...] = ()
    weights_licence: str | None = None

    @property
    def local_environment(self) -> Path | None:
        """The virtual environment this backend runs from, if it has one.

        Returns:
            The directory, or ``None`` for a backend that is reached over HTTP
            and installed nowhere on this machine.
        """
        return None


class HeavyConverter(HeavyTier, SubprocessConverter):
    """A GPU-tier converter, run from an environment of its own.

    Subclasses declare :attr:`command`, :attr:`weights_licence` and
    :attr:`install_steps`, and implement :meth:`build_argv` and
    :meth:`read_output`.

    Attributes:
        command: The console script the backend's package installs.
        downloads_models: Whether a first run fetches weights over the network.
    """

    command: str
    downloads_models: bool = True

    # ---------------------------------------------------------------- discovery

    @property
    def environment(self) -> Path:
        """The conventional environment directory for this backend.

        Returns:
            The path.
        """
        return environment_root(self.info.id)

    @property
    def local_environment(self) -> Path | None:
        """The environment this backend runs from.

        Returns:
            :attr:`environment`, which is what ``doctor`` asks PyTorch about.
        """
        return self.environment

    @property
    def extra_key(self) -> str:
        """The ``--extra`` key that points at a non-standard environment.

        Returns:
            ``<backend id>_python``.
        """
        return _EXTRA_TEMPLATE.format(backend_id=self.info.id)

    def discover(self) -> str | None:
        """Locate this backend's command, cached for the life of the instance.

        Three places, in order, and nothing beyond them:

        1. The conventional environment, ``~/.local/share/tokenmill/<id>/``,
           which is what :attr:`install_steps` tells people to create.
        2. A ``.venv-<id>`` beside the working directory, for someone who keeps
           their environments with their project.
        3. ``PATH``, for someone who installed it globally and meant to.

        Nothing is guessed at beyond those, and in particular no attempt is made
        to find a conda environment or a version manager's shims: a converter
        that ran *some* Marker it found lying around would produce output nobody
        could attribute.

        Returns:
            The absolute path to the command, or ``None``.
        """
        if self._resolved is not None:
            return self._resolved

        candidates: list[Path] = []
        for root in (self.environment, Path.cwd() / f".venv-{self.info.id}"):
            candidates.extend(root / sub / self.command for sub in interpreter_names())
            if sys.platform == "win32":
                candidates.extend(root / sub / f"{self.command}.exe" for sub in interpreter_names())

        for candidate in candidates:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                self._resolved = str(candidate)
                return self._resolved

        return super().discover()

    def configured_command(self, options: ConvertOptions) -> str | None:
        """Return an explicitly configured command path, if the user gave one.

        Args:
            options: May carry ``--extra <id>_python=/path/to/env/bin/<cmd>``.

        Returns:
            The configured path, or ``None``.
        """
        value = options.extra.get(self.extra_key)
        return value.strip() if isinstance(value, str) and value.strip() else None

    def _probe(self) -> Availability:
        """Report availability by looking for the command.

        **Deliberately does not check for a GPU.** A backend that vanished from
        the listing on a CPU-only machine would leave a user with no way to see
        that it exists or what it would take to use it, and every one of these
        will at least *start* without a GPU — slowly, or with a clear error of
        its own. ``tokenmill doctor`` is where the hardware question is answered.

        Returns:
            Present when the command was found, otherwise a missing binary
            carrying the full install sequence.
        """
        if self.discover() is None:
            return Availability.missing_binary(self.command, hint=self.install_hint())
        return Availability.present()

    def install_hint(self) -> str:
        """Build the install instructions for this backend.

        Returns:
            The commands, joined so they can be pasted, followed by a pointer
            at the documentation for the hardware and licence conditions.
        """
        steps = self.install_steps or (
            f"python -m venv {self.environment}",
            f"{self.environment}/bin/pip install <the backend's package>",
        )
        return (
            f"{' && '.join(steps)} "
            f"(or point tokenmill at an existing environment with "
            f"--extra {self.extra_key}=/path/to/env/bin/{self.command}). "
            f"See docs/BACKENDS.md for the hardware this needs and the licence "
            f"conditions on its weights."
        )

    # ------------------------------------------------------------------ running

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Convert, after checking the permissions a model download needs.

        Args:
            source: The document to convert.
            options: Supplies the timeout, the network permission and any
                ``--extra`` overrides.
            context: Collects metadata and warnings.

        Returns:
            The converted text.

        Raises:
            NetworkRequired: If the backend may need to download weights and
                network access has not been permitted.
            ConversionError: On any other failure, already in the taxonomy.
        """
        configured = self.configured_command(options)
        if configured is not None:
            self._resolved = configured

        if self.downloads_models and not options.allow_network:
            raise NetworkRequired(
                f"{self.info.id} downloads its model weights on first use, which is a "
                f"multi-gigabyte network operation",
                backend_id=self.info.id,
                hint=(
                    "pass --allow-network to permit it, or run the backend once by hand "
                    "so its cache is populated. tokenmill cannot tell an already-cached "
                    "model from one about to be fetched without asking the backend, "
                    "which is itself the expensive part"
                ),
            )

        context.note("weights_licence", self.weights_licence or "unverified")
        context.note("requires_gpu", self.info.requires_gpu)
        return super()._convert(source, options, context)

    def run_conversion(
        self,
        source: Source,
        options: ConvertOptions,
        context: ConversionContext,
        workspace: Path,
    ) -> str:
        """Run the backend over one document and read what it wrote.

        Args:
            source: The document.
            options: Supplies the timeout.
            context: Collects metadata and warnings.
            workspace: A private directory, removed afterwards.

        Returns:
            The extracted Markdown.

        Raises:
            BackendFailed: If the source has no path, or the tool wrote nothing.
        """
        if source.path is None:
            raise BackendFailed(
                f"{self.info.id} converts a file on disk and this source has no path",
                backend_id=self.info.id,
                hint="pass a file rather than raw bytes",
            )

        outdir = workspace / "out"
        outdir.mkdir()
        argv = self.build_argv(source.path, outdir)
        result = self.run(argv, options=options, cwd=workspace)

        text = self.read_output(outdir, source.path)
        if text is None:
            raise BackendFailed(
                f"{self.info.id} wrote no Markdown for {source.name}",
                backend_id=self.info.id,
                stderr=result.stderr,
                hint=(
                    "check the backend's own output above; on a machine with no GPU "
                    "these tools often fail at model load rather than at conversion"
                ),
            )
        context.note("tool", self.command)
        return text

    @abstractmethod
    def build_argv(self, source: Path, outdir: Path) -> list[str]:
        """Build the arguments this backend is invoked with.

        Args:
            source: The document to convert.
            outdir: An empty directory to write into.

        Returns:
            The arguments **after** the executable.
        """

    @abstractmethod
    def read_output(self, outdir: Path, source: Path) -> str | None:
        """Find and read the Markdown the backend produced.

        Args:
            outdir: The directory it was told to write into.
            source: The original document, for backends that name their output
                after it.

        Returns:
            The Markdown, or ``None`` when nothing was produced — which every
            one of these signals by writing no file rather than by exiting
            non-zero.
        """


def first_markdown(outdir: Path, *, extensions: Sequence[str] = (".md", ".markdown")) -> str | None:
    """Return the first Markdown file under ``outdir``, searched recursively.

    Every backend here writes into a directory whose layout differs — some nest
    a folder per document, some write beside the input's name — and all of them
    write exactly one Markdown file per conversion. Searching rather than
    predicting means a layout change upstream costs nothing.

    Args:
        outdir: The directory to search.
        extensions: Which suffixes count as Markdown.

    Returns:
        The file's text, or ``None`` when there is no such file.
    """
    found = sorted(
        path
        for path in outdir.rglob("*")
        if path.is_file() and path.suffix.lower() in {e.lower() for e in extensions}
    )
    if not found:
        return None
    return found[0].read_text(encoding="utf-8", errors="replace")
