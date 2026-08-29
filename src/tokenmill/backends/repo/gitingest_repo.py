"""The ``gitingest`` backend: a repository as one prompt-ready file.

The Python-native member of the repository tier and the one auto-selection
picks, for the same reason ``pdfplumber`` leads for PDFs: it is importable, so
there is no external runtime to find, no version to guess at and no process to
supervise. ``RESEARCH.md`` Category 5 reaches the same conclusion —
*"gitingest is the best Python-native fit (importable, tiktoken counts)"*.

**What it produces.** A summary, a directory tree, and every file's contents
under a header, in one document:

```
Directory structure:
└── sample_repo/
    ├── README.md
    ├── pyproject.toml
    ├── docs/
    │   └── design.md
    └── src/
        └── widgetlib/
            ├── __init__.py
            ├── core.py
            └── utils.py

================================================
FILE: README.md
================================================
# widgetlib
...
```

**What it leaves out, correctly.** On ``tests/fixtures/sample_repo`` it packs 7
of the 9 tracked files: ``assets/logo.bin`` is skipped as binary and
``.gitignore`` as a dot file, and the ``.gitignore``d ``secrets.env`` never
appears at all. That last one is the property the fixture exists to check — its
sentinel string must never reach a model's context — and a test asserts it.

**Two things this adapter does that gitingest does not do for you.**

*The token budget is tokenmill's, not gitingest's.* gitingest computes its own
estimate with tiktoken and prints it in the summary; that number is not
tokenmill's measurement, is in a tokenizer the user did not choose, and does
nothing to cap the output. tokenmill parses the pack back into per-file
sections and applies one budget, in the run's own tokenizer, across all three
repository backends — see :mod:`tokenmill.backends.repo._common`.

*A local ingestion is not allowed to read a GitHub token.* ``resolve_token``
falls back to ``$GITHUB_TOKEN`` and **validates its format**, unconditionally,
before it has looked at the source at all. A malformed token in the environment
therefore fails a purely local packing with
``InvalidGitHubTokenError``, which is a confusing way to be told about a
variable that had nothing to do with the request. Found by hitting it. The
adapter clears the variable for the duration of the call.

License: gitingest is MIT, verified against the installed package metadata
(0.3.1). It is in the ``repo`` extra rather than the core install: it requires
``starlette``, ``pydantic``, ``httpx`` and ``loguru``, which is a web-service
stack in a command-line tool's default dependency set. See ``PROGRESS.md`` for
the measurement and the reasoning.
"""

from __future__ import annotations

import contextlib
import os
import warnings
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from tokenmill.backends._common import classify_failure, probe_module
from tokenmill.backends.repo._common import (
    PackedFile,
    RepoOptions,
    apply_budget,
    directory_totals,
    full_pack,
    note_repo_metadata,
    read_repo_options,
    repo_workdir,
    split_sections,
)
from tokenmill.core.errors import ConversionError
from tokenmill.core.globalstate import process_global_state
from tokenmill.core.models import (
    Availability,
    BackendInfo,
    ConvertOptions,
    Domain,
    LicenseTier,
    OutputFormat,
    Source,
)
from tokenmill.core.protocol import BaseConverter, ConversionContext
from tokenmill.tokens.registry import default_tokenizer_registry

__all__ = ["GitingestConverter"]


class GitingestConverter(BaseConverter):
    """Packs a repository into one document with gitingest.

    Attributes:
        info: Static metadata for this backend.
    """

    info = BackendInfo(
        id="gitingest",
        name="gitingest",
        description=(
            "Packs a repository into one prompt-ready document with a "
            "directory tree and every file's contents. Python-native, so no "
            "external runtime is needed."
        ),
        domains=(Domain.REPO,),
        input_formats=("repo",),
        output_formats=(OutputFormat.MARKDOWN, OutputFormat.TEXT),
        license="MIT",
        license_tier=LicenseTier.PERMISSIVE,
        upstream_url="https://github.com/coderamp-labs/gitingest",
        install_extra="repo",
        priority=60,
    )

    def _probe(self) -> Availability:
        """Check that gitingest is importable.

        Returns:
            Present when gitingest is installed, otherwise a missing dependency
            with the install command.
        """
        return probe_module("gitingest", install_extra="repo")

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Pack the repository and apply tokenmill's shared repository options.

        Args:
            source: The repository — a local directory, or a Git URL that
                :func:`~tokenmill.backends.repo._common.repo_workdir` clones
                into a temporary directory and removes afterwards.
            options: Supplies the repository settings in ``extra``, and the
                tokenizer the budget is counted in.
            context: Collects the pack's structured facts and any warning.

        Returns:
            The packed repository.

        Raises:
            ConversionError: If gitingest cannot read the repository.
        """
        settings = read_repo_options(options)

        with repo_workdir(source, options, self.info.id) as root:
            tree, content = self._ingest(root, settings, context)

        preamble, sections = split_sections(f"{tree}\n\n{content}", "gitingest")
        if not sections and content.strip():
            # The pack is not empty but no header matched, so the budget and the
            # breakdown cannot be computed. Say so rather than reporting a
            # file count of zero, which would read as an empty repository.
            context.warn(
                "gitingest's output format was not recognised, so the token budget and "
                "the per-directory breakdown could not be applied to it. The pack itself "
                "is complete and unmodified; this is a tokenmill parsing problem, not a "
                "problem with your repository"
            )

        return self._finish(preamble, sections, settings, options, context, root_name=source.name)

    def _ingest(
        self, root: Path, settings: RepoOptions, context: ConversionContext
    ) -> tuple[str, str]:
        """Call gitingest and return its tree and its file contents.

        Args:
            root: The directory to pack.
            settings: The repository options to translate into gitingest's.
            context: Collects a warning if the summary is unusable.

        Returns:
            The directory tree and the concatenated file contents.

        Raises:
            ConversionError: If gitingest fails.
        """
        ingest = _load_gitingest()
        try:
            # Defect D2: all three of these manipulate process-global state, so
            # they are held under the one lock. Unlike the document adapters,
            # whose blocks cover only an import, these have to cover the whole
            # call — pathspec warns while gitingest builds its ignore rules,
            # loguru's registry has to stay set while it logs, and
            # `GITHUB_TOKEN` is read at the top of `ingest`. So **two gitingest
            # conversions cannot overlap**, and `docs/BENCHMARKS.md` says what
            # that costs a parallel batch.
            with (
                process_global_state("gitingest conversion"),
                _without_github_token(),
                _quiet_gitingest(),
                _without_pathspec_deprecation(),
            ):
                summary, tree, content = ingest(
                    str(root),
                    max_file_size=settings.max_file_bytes,
                    include_patterns=set(settings.include) or None,
                    exclude_patterns=set(settings.exclude) or None,
                    include_gitignored=not settings.respect_gitignore,
                    include_submodules=False,
                )
        except ConversionError:
            raise
        except Exception as exc:
            raise classify_failure(
                exc, source=Source.from_path(root), backend_id=self.info.id
            ) from exc

        # gitingest's summary carries its own tiktoken estimate, in a tokenizer
        # the user did not choose and against no budget. It is deliberately not
        # forwarded: tokenmill measures in the pipeline, and two token figures
        # from different tokenizers in one document is exactly the confusion
        # `TokenCount` exists to prevent.
        for line in str(summary).splitlines():
            if line.lower().startswith("files analyzed:"):
                context.note("files_analyzed", line.split(":", 1)[1].strip())
        return str(tree), str(content)

    def _finish(
        self,
        preamble: str,
        sections: list[PackedFile],
        settings: RepoOptions,
        options: ConvertOptions,
        context: ConversionContext,
        *,
        root_name: str,
    ) -> str:
        """Apply the budget and the breakdown, and assemble the final document.

        Args:
            preamble: The summary and directory tree.
            sections: The per-file sections.
            settings: The repository options.
            options: Supplies the tokenizer.
            context: Collects the notes and warnings.
            root_name: The repository's display name.

        Returns:
            The final packed text.
        """
        counter, unit = _counter_for(options, context, wanted=settings.token_budget is not None)

        text, report = apply_budget(
            preamble, sections, budget=settings.token_budget, count=counter, unit=unit
        )
        if report.over_budget:
            context.warn(
                f"the pack is {report.emitted:,} {unit}, over the "
                f"{report.budget:,}-{unit} budget: the directory tree alone does not fit, "
                f"and it is never dropped because it is what says which files are missing"
            )
        if report.dropped:
            context.warn(
                f"{report.dropped_count} file(s) were dropped to fit the "
                f"{report.budget:,}-{unit} budget: "
                f"{', '.join(path for path, _ in report.dropped[:5])}"
                f"{', ...' if report.dropped_count > 5 else ''}. "
                f"The full pack would have been {report.total:,} {unit}"
            )

        if settings.tree_tokens and counter is not None and sections:
            breakdown = directory_totals(sections, count=counter, unit=unit)
            if breakdown:
                text += f"\n\n---\n\n## Tokens by directory ({unit})\n\n{breakdown}\n"

        note_repo_metadata(
            context,
            root=Path(root_name),
            tool="gitingest",
            sections=sections,
            report=report,
            full_text=full_pack(preamble, sections) if report.dropped else None,
        )
        return text


#: The imported ``gitingest.ingest``, cached after the first use.
#:
#: Cached because **the import is the expensive and dangerous part**, not the
#: call: it installs a loguru ``InterceptHandler`` on the stdlib root logger and
#: drops that logger's level to 0. Doing it once, behind the lock, means the
#: logging repair happens once too — where before it was a snapshot-and-restore
#: of unchanged state on every single conversion, inside the block that
#: serialises them.
_INGEST: Any = None


def _load_gitingest() -> Any:
    """Import ``gitingest.ingest`` once, repairing the logging it breaks.

    Imported here rather than at module scope: ``CONTRIBUTING.md`` rule 3, and
    this one matters more than most, because the import has side effects on the
    host process.

    Returns:
        The ``ingest`` callable.

    Raises:
        ImportError: If gitingest is not installed. The adapter's probe reports
            that first, so reaching this is a caller that ignored it.
    """
    global _INGEST  # a deliberate write-once cache; see the note above
    if _INGEST is not None:
        return _INGEST
    with process_global_state("importing gitingest"), _preserve_stdlib_logging():
        from gitingest import ingest
    _INGEST = ingest
    return ingest


def _counter_for(
    options: ConvertOptions, context: ConversionContext, *, wanted: bool
) -> tuple[Any, str]:
    """Return a counting function for the run's tokenizer, or ``None``.

    A backend consulting a tokenizer is the one exception to "backends do not
    measure", and it is narrow: the count shapes what the converter *emits*, in
    obedience to a limit the user set. Nothing counted here is reported as a
    measurement; the pipeline still does all of that.

    Args:
        options: Supplies the tokenizer id.
        context: Collects a warning when the tokenizer cannot be loaded.
        wanted: Whether the caller actually needs a counter. When no budget and
            no breakdown were asked for, a tokenizer that cannot load is not
            worth a warning.

    Returns:
        The counting callable and the tokenizer id, or ``(None, id)``.
    """
    try:
        counter = default_tokenizer_registry().get(options.tokenizer)
    except Exception as exc:
        if wanted:
            # Never silently ignored: a cap that quietly did nothing is worse
            # than no cap, because the user believes the output is bounded.
            context.warn(
                f"the token budget could not be applied: tokenizer "
                f"{options.tokenizer!r} could not be loaded ({exc}). The whole "
                f"repository was packed"
            )
        return None, options.tokenizer
    return counter.count, counter.info.id


@contextlib.contextmanager
def _preserve_stdlib_logging() -> Iterator[None]:
    """Undo gitingest's reconfiguration of the *host's* logging.

    Importing gitingest installs a loguru ``InterceptHandler`` on the standard
    library's **root** logger and sets that logger's level to ``0``. Measured,
    not guessed:

    ```
    root handlers before: []                    level 30
    root handlers after:  ['InterceptHandler']  level 0
    ```

    Two consequences, both bad and neither the user's doing. Every record
    tokenmill logs — and every record the *application embedding tokenmill*
    logs — is rerouted through loguru's formatter; and the root level dropping
    from WARNING to NOTSET means DEBUG and INFO records that were deliberately
    suppressed start appearing. A single ``tokenmill repo`` printed one of
    tokenmill's own INFO lines in loguru's format, which is how this was found.

    A backend is allowed to be noisy about itself. It is not allowed to
    reconfigure the process it was imported into. The root logger's handlers and
    level are snapshotted and put back.

    This manipulates process-global state and is not thread-safe (defect D2).
    It is entered from :func:`_load_gitingest`, under the process-global lock
    and **once** — the import is what reconfigures logging, so repeating the
    snapshot-and-restore per conversion was protecting unchanged state at the
    cost of holding the lock for every pack.

    Yields:
        Nothing; the logging configuration is restored on the way out.
    """
    import logging

    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    try:
        yield
    finally:
        root.handlers[:] = handlers
        root.setLevel(level)


@contextlib.contextmanager
def _without_pathspec_deprecation() -> Iterator[None]:
    """Keep pathspec's deprecation warning from failing the conversion.

    gitingest builds its ignore rules with ``PathSpec.from_lines("gitwildmatch",
    ...)``, and current pathspec deprecates that factory name in favour of
    ``"gitignore"``. Under ``filterwarnings = ["error"]`` — which this project's
    own test suite sets, and which applications embedding tokenmill may set too
    — that warning becomes an exception inside gitingest, and a perfectly
    healthy backend is reported as ``BackendFailed``.

    Filtered rather than forwarded to the user, which is the distinction Phase 2
    drew and this follows: an import-time warning about *the user's platform*
    ("your Windows version is unsupported") is worth hearing and becomes a
    conversion warning, while a library's internal deprecation churn is
    something only its maintainers can act on. Docling's own deprecated-field
    warning is filtered for the same reason.

    Scoped to that one message, so an unrelated ``DeprecationWarning`` from
    anywhere else still surfaces. Found the same way Phase 2's was: by running
    the suite, where the CLI had worked because it does not set ``-W error``.

    :func:`warnings.catch_warnings` manipulates global state and is not
    thread-safe (defect D2). This is entered from inside
    :func:`~tokenmill.core.globalstate.process_global_state` in ``_ingest``
    rather than acquiring the lock itself, because all four of gitingest's
    global-state blocks cover the same call and four nested acquires of one
    reentrant lock is noise. The lock is reentrant, so a caller that does
    acquire it separately is safe too.

    Yields:
        Nothing; the filter is active for the duration of the block.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r".*gitwildmatch.*is deprecated",
            category=DeprecationWarning,
        )
        yield


@contextlib.contextmanager
def _quiet_gitingest() -> Iterator[None]:
    """Silence gitingest's own logging for the duration of the block.

    Entered from inside :func:`~tokenmill.core.globalstate.process_global_state`
    in ``_ingest``: loguru's activation registry is process-global, and two
    threads toggling it race (defect D2).

    gitingest logs at INFO through loguru, whose default sink is stderr, so a
    single ``tokenmill repo`` printed eight lines of a dependency's internal
    progress before the report — including one WARNING about a tiktoken download
    tokenmill neither asked for nor uses. A wrapper whose output is a
    dependency's log is not one product.

    ``logger.disable("gitingest")`` suppresses records emitted from that package
    only, which is exactly the scope wanted: nothing tokenmill or a host
    application logs is affected. It is re-enabled afterwards.

    The one caveat, stated because it is a real if small cost: loguru's
    activation registry has no "what was it before" query, so re-enabling is
    unconditional. An application that had deliberately disabled gitingest's
    logger before calling tokenmill will find it enabled again. Nothing in this
    project does that, and the alternative — leaving a dependency's logging on
    by default — is worse for every user.

    Yields:
        Nothing; logging is restored on the way out.
    """
    try:
        from loguru import logger
    except ImportError:  # pragma: no cover - loguru is a gitingest dependency
        yield
        return
    logger.disable("gitingest")
    try:
        yield
    finally:
        logger.enable("gitingest")


@contextlib.contextmanager
def _without_github_token() -> Iterator[None]:
    """Hide ``$GITHUB_TOKEN`` from gitingest for the duration of the block.

    gitingest's ``resolve_token`` falls back to the environment variable and
    validates its *format* before looking at the source, so a malformed token —
    and "malformed" includes any placeholder a CI system or a development
    sandbox happens to export — fails a purely local packing with
    ``InvalidGitHubTokenError``. Found by hitting it in this project's own
    sandbox, where ``GITHUB_TOKEN`` is set to a proxy placeholder.

    tokenmill does its own cloning, through ``git``, which uses the user's
    normal credential helper or SSH agent. So gitingest is only ever handed a
    local path here and has no legitimate use for a token at all.

    This manipulates process-global state and is not thread-safe (defect D2):
    two threads that each pop the variable and restore it lose it from the
    process entirely, because the second pop reads ``None`` and the second
    restore writes nothing. Entered from inside
    :func:`~tokenmill.core.globalstate.process_global_state` in ``_ingest``.

    **There is no API alternative, and it was checked rather than assumed.**
    ``ingest()`` takes a ``token`` argument, but gitingest resolves it as
    ``token or os.getenv("GITHUB_TOKEN")`` — so passing ``None`` or ``""``
    falls back to the environment, and passing a placeholder trips its own
    ``validate_github_token``. Removing the variable is the only way to say
    "there is no token", which matters because an unusually-formatted one in a
    user's shell would otherwise fail a purely local pack.

    Yields:
        Nothing; the variables are restored on the way out.
    """
    saved = {name: os.environ.pop(name, None) for name in ("GITHUB_TOKEN", "GH_TOKEN")}
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is not None:
                os.environ[name] = value
