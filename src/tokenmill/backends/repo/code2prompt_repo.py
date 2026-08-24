"""The ``code2prompt`` backend: the Rust one, wrapped as a child process.

The third member of the repository tier, and the fastest of the three on a large
tree — it is Rust, and it shows. ``RESEARCH.md`` Category 5 lists it at ~7.4k
stars with a Python SDK over its core; this adapter wraps the **binary** rather
than the SDK, because the SDK is a binding to the same Rust code and a
subprocess boundary costs nothing here while removing a compiled dependency from
the install entirely.

**Installation is the reason it is ranked last**, not quality. There is no
wheel: ``cargo install code2prompt`` compiles it, which needs a Rust toolchain
and a few minutes. A user who has one gets a fast packer; a user who does not
gets a clear message naming the command, and gitingest — which needs nothing but
the ``repo`` extra — handles their repository instead.

**Verified here.** ``cargo install code2prompt`` succeeded in this project's own
sandbox and produced **4.3.0**, which is worth recording because the Phase 3/4
handover expected it to fail: ``crates.io``'s *API* is blocked by this
environment's egress policy, but ``index.crates.io`` and ``static.crates.io`` —
the hosts cargo actually uses — are not.

**Security.** List arguments, never ``shell=True``, ``--`` before the positional
path, and a path beginning with ``-`` refused rather than passed.

License: code2prompt is MIT (``RESEARCH.md`` Category 5). It runs out of
process, so its licence never touches ours.
"""

from __future__ import annotations

from pathlib import Path

from tokenmill.backends._subprocess import probe_tool, run_tool, safe_path_argument
from tokenmill.backends.repo._common import (
    RepoOptions,
    apply_budget,
    directory_totals,
    full_pack,
    note_repo_metadata,
    read_repo_options,
    repo_workdir,
    split_sections,
)
from tokenmill.backends.repo.gitingest_repo import _counter_for
from tokenmill.core.errors import BackendFailed
from tokenmill.core.models import (
    Availability,
    BackendInfo,
    ConvertOptions,
    Domain,
    IsolationMode,
    LicenseTier,
    OutputFormat,
    Source,
)
from tokenmill.core.protocol import BaseConverter, ConversionContext

__all__ = ["Code2PromptConverter"]

#: There is no wheel and no npm package; it is compiled from source.
_INSTALL_HINT = (
    "install a Rust toolchain (https://rustup.rs) then run "
    "'cargo install code2prompt', or use --backend gitingest, which needs no "
    "external tool"
)


class Code2PromptConverter(BaseConverter):
    """Packs a repository into one document with code2prompt, out of process.

    Attributes:
        info: Static metadata for this backend.
    """

    info = BackendInfo(
        id="code2prompt",
        name="code2prompt",
        description=(
            "Packs a repository with code2prompt. A Rust binary, so it runs as "
            "a child process and must be installed with cargo; the fastest of "
            "the three on a large tree."
        ),
        domains=(Domain.REPO,),
        input_formats=("repo",),
        output_formats=(OutputFormat.MARKDOWN,),
        license="MIT",
        license_tier=LicenseTier.PERMISSIVE,
        upstream_url="https://github.com/mufeedvh/code2prompt",
        install_extra=None,
        isolation=IsolationMode.SUBPROCESS,
        requires_binary="code2prompt",
        priority=20,
    )

    def _probe(self) -> Availability:
        """Check for ``code2prompt`` on ``PATH``.

        Unlike Repomix there is no ``npx`` equivalent — no way to fetch and run
        it in one step — so absence is simply absence, with the cargo command
        that fixes it.

        Returns:
            Present when the binary is on ``PATH``, otherwise a missing binary
            carrying the install command.
        """
        return probe_tool("code2prompt", hint=_INSTALL_HINT)

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Pack the repository with code2prompt.

        Args:
            source: The repository — a local directory, or a Git URL that
                :func:`~tokenmill.backends.repo._common.repo_workdir` clones and
                removes afterwards.
            options: Supplies the repository settings and the timeout.
            context: Collects the pack's structured facts and any warning.

        Returns:
            The packed repository.

        Raises:
            BackendFailed: If code2prompt exits non-zero, or writes nothing.
        """
        settings = read_repo_options(options)

        with repo_workdir(source, options, self.info.id) as root:
            argv = [
                "code2prompt",
                *self._arguments(settings),
                "--",
                safe_path_argument(root, backend_id=self.info.id),
            ]
            result = run_tool(argv, backend_id=self.info.id, timeout_s=options.timeout_s, cwd=root)

        packed = result.stdout
        if not packed.strip():
            raise BackendFailed(
                f"code2prompt produced no output for {source.name}",
                backend_id=self.info.id,
                stderr=result.stderr,
                hint="check the include and exclude patterns actually match some files",
            )

        preamble, sections = split_sections(packed, "code2prompt")
        if not sections:
            context.warn(
                "code2prompt's Markdown format was not recognised, so the token budget "
                "and the per-directory breakdown could not be applied. The pack itself "
                "is complete and unmodified; this is a tokenmill parsing problem"
            )

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
                f"{report.budget:,}-{unit} budget. The full pack would have been "
                f"{report.total:,} {unit}"
            )

        if settings.tree_tokens and counter is not None and sections:
            breakdown = directory_totals(sections, count=counter, unit=unit)
            if breakdown:
                text += f"\n\n---\n\n## Tokens by directory ({unit})\n\n{breakdown}\n"

        note_repo_metadata(
            context,
            root=Path(source.name),
            tool="code2prompt",
            sections=sections,
            report=report,
            full_text=full_pack(preamble, sections) if report.dropped else None,
        )
        return text

    @staticmethod
    def _arguments(settings: RepoOptions) -> list[str]:
        """Translate tokenmill's repository options into code2prompt's flags.

        Args:
            settings: The options to translate.

        Returns:
            The flags, without the binary or the target.
        """
        argv = [
            # "-" means stdout, so nothing is written into the user's tree.
            "--output-file",
            "-",
            "--output-format",
            "markdown",
            "--full-directory-tree",
            "--quiet",
        ]
        for pattern in settings.include:
            argv += ["--include", pattern]
        for pattern in settings.exclude:
            argv += ["--exclude", pattern]
        if not settings.respect_gitignore:
            argv.append("--no-ignore")
        return argv
