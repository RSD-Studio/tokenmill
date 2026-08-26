"""The ``repomix`` backend: the category leader, wrapped as a child process.

Repomix is the most-used tool in this category — ``RESEARCH.md`` Category 5 puts
it at ~26.8k stars against gitingest's ~15.3k — and it is TypeScript. There is
no way to import it into a Python process, so it is invoked as a child process
through ``npx``, and this adapter's entire job is to make that indistinguishable
from the in-process backends: same options, same errors, same budget, same
per-directory breakdown.

**It is not the default, despite being the category leader.** Running it means
finding a Node runtime, and on a machine without one the first thing a user
would see from ``tokenmill convert ./my-repo`` is a missing-binary message.
gitingest needs nothing beyond the ``repo`` extra, so it leads and this is
reachable by name — the same reasoning that keeps docling off the default PDF
path.

**What ``npx`` costs, said out loud.** Without a locally installed ``repomix``,
``npx`` downloads the package on first use. That is a network fetch inside a
command the user may have believed was local, so this adapter **requires
``--allow-network`` when it has to go through ``npx``**, and does not when
``repomix`` is already on ``PATH``. Installing it once with
``npm install -g repomix`` removes the condition entirely, and the missing-binary
hint says so.

**What its options do not quite mean.** Repomix's own ``--token-budget`` makes
it *fail* with a non-zero exit when the pack is too big; it does not truncate.
tokenmill's ``--token-budget`` truncates and reports what it dropped, in the
run's own tokenizer, identically across all three repository backends. The two
are not the same feature and this adapter does not pass ours through as theirs.

**Security.** List arguments, never ``shell=True``, ``--`` before every
positional, and a path beginning with ``-`` is refused rather than passed. A
repository path is attacker-controlled input the moment someone runs tokenmill
on a checkout they did not write, and the plan's risk register names this by
name.

License: Repomix is MIT (``RESEARCH.md`` Category 5, verified against the
published package: ``npx repomix@latest --version`` reports 1.18.0 here). It
runs out of process, so its licence never touches ours — but MIT would allow
importing it anyway if it were Python.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tokenmill.backends._subprocess import find_tool, run_tool, safe_path_argument
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
from tokenmill.core.errors import BackendFailed, NetworkRequired
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

__all__ = ["RepomixConverter"]

#: How to get a `repomix` that needs no network on every run.
_INSTALL_HINT = (
    "install Node.js, then either 'npm install -g repomix' (recommended: no "
    "download per run) or pass --allow-network to let npx fetch it each time"
)

#: What to say when this backend was *auto-selected* and cannot run without a
#: download.
#:
#: A clean `pip install tokenmill` has no `repo` extra, so gitingest is absent
#: and the chain falls to this backend — which reports itself available because
#: `npx` exists. A user who typed `tokenmill repo ./project` then gets a Node
#: error about a tool they never chose, with no mention of the Python one that
#: would just work. Found by doing the clean-install check by hand.
_AUTOSELECTED_HINT = (
    'pip install "tokenmill[repo]" for the Python backend, which needs no '
    "external tool; or " + _INSTALL_HINT
)

#: Extra wall-clock granted when `npx` has to fetch Repomix before it can run.
#:
#: `options.timeout_s` is a budget for a *conversion*. When `repomix` is already
#: on PATH that is all it pays for, and packing this project's `sample_repo`
#: fixture takes about 2 s. When the launcher is `npx`, the very same budget
#: silently also pays for downloading and installing an npm package on first
#: use — a different job with a wildly different cost. Measured cold: 6.8 s in
#: this Linux container, and more than the whole 120 s default on a GitHub
#: Windows runner, where it timed out `TestRepomix::test_it_packs_the_repository`
#: on the py3.13 cell of CI run 85 and the py3.12 cell of run 87 while the other
#: two Windows cells passed. The conversion there would have taken seconds; the
#: install is what did not fit.
#:
#: So the fetch gets its own allowance instead of eating the user's. Someone who
#: passed `--timeout 30` still gets 30 s of *packing*: they do not also get 30 s
#: to install Node software they may not have realised was being installed.
#: `npm install -g repomix` removes the fetch, and with it this allowance.
_NPX_FETCH_ALLOWANCE_S: Final = 180.0


class RepomixConverter(BaseConverter):
    """Packs a repository into one document with Repomix, out of process.

    Attributes:
        info: Static metadata for this backend.
    """

    info = BackendInfo(
        id="repomix",
        name="Repomix",
        description=(
            "Packs a repository with Repomix, the category leader. A Node "
            "program, so it runs as a child process; needs repomix on PATH or "
            "npx plus --allow-network."
        ),
        domains=(Domain.REPO,),
        input_formats=("repo",),
        output_formats=(OutputFormat.MARKDOWN,),
        license="MIT",
        license_tier=LicenseTier.PERMISSIVE,
        upstream_url="https://github.com/yamadashy/repomix",
        install_extra=None,
        isolation=IsolationMode.SUBPROCESS,
        requires_binary="repomix",
        priority=40,
    )

    def _probe(self) -> Availability:
        """Check for ``repomix`` on ``PATH``, or ``npx`` to fetch it with.

        Both are reported as available, because both can produce a pack. The
        difference — that ``npx`` downloads on first use — is enforced at
        conversion time, where the ``allow_network`` setting is known, rather
        than here where it is not.

        Returns:
            Present when either is on ``PATH``, otherwise a missing binary with
            the install command.
        """
        if find_tool("repomix") is not None or find_tool("npx") is not None:
            return Availability.present()
        return Availability.missing_binary("repomix", hint=_INSTALL_HINT)

    def _convert(self, source: Source, options: ConvertOptions, context: ConversionContext) -> str:
        """Pack the repository with Repomix.

        Args:
            source: The repository — a local directory, or a Git URL that
                :func:`~tokenmill.backends.repo._common.repo_workdir` clones and
                removes afterwards.
            options: Supplies the repository settings, the timeout and the
                network permission.
            context: Collects the pack's structured facts and any warning.

        Returns:
            The packed repository.

        Raises:
            NetworkRequired: If ``repomix`` is absent and running it through
                ``npx`` would download it without permission.
            BackendFailed: If Repomix exits non-zero, or writes nothing.
        """
        settings = read_repo_options(options)
        launcher, fetches_package = self._launcher(options)

        # See _NPX_FETCH_ALLOWANCE_S: the npx path has to install the package
        # before it can run it, and that install is not part of the conversion
        # the user set a budget for.
        budget = options.timeout_s + (_NPX_FETCH_ALLOWANCE_S if fetches_package else 0.0)

        with repo_workdir(source, options, self.info.id) as root:
            argv = [*launcher, *self._arguments(settings), "--", _target(root, self.info.id)]
            result = run_tool(
                argv,
                backend_id=self.info.id,
                timeout_s=budget,
                cwd=root,
            )

        packed = result.stdout
        if not packed.strip():
            raise BackendFailed(
                f"repomix produced no output for {source.name}",
                backend_id=self.info.id,
                stderr=result.stderr,
                hint="check the include and exclude patterns actually match some files",
            )

        preamble, sections = split_sections(packed, "repomix")
        if not sections:
            context.warn(
                "repomix's Markdown format was not recognised, so the token budget and "
                "the per-directory breakdown could not be applied. The pack itself is "
                "complete and unmodified; this is a tokenmill parsing problem"
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
            tool="repomix",
            sections=sections,
            report=report,
            full_text=full_pack(preamble, sections) if report.dropped else None,
        )
        return text

    def _launcher(self, options: ConvertOptions) -> tuple[list[str], bool]:
        """Return the command that runs Repomix, preferring an installed one.

        Args:
            options: Supplies ``allow_network``.

        Returns:
            The launcher prefix, and whether running it will first **fetch** the
            package. The caller needs the second half because a fetch is not a
            conversion and must not be timed as one; see
            :data:`_NPX_FETCH_ALLOWANCE_S`.

        Raises:
            NetworkRequired: If only ``npx`` is available and network access has
                not been permitted, since ``npx`` downloads the package.
        """
        installed = find_tool("repomix")
        if installed is not None:
            return [installed], False
        if not options.allow_network:
            # The hint depends on whether the user chose this backend. Someone
            # who typed `--backend repomix` wants repomix; someone who typed
            # `tokenmill repo ./project` on a core-only install has landed here
            # by elimination and mostly wants a working answer.
            chosen = options.backend == self.info.id
            raise NetworkRequired(
                "repomix is not installed, and running it through npx would download it",
                backend_id=self.info.id,
                hint=_INSTALL_HINT if chosen else _AUTOSELECTED_HINT,
            )
        # `--yes` so npx never stops to ask; stdin is closed, so a prompt would
        # hang forever holding a terminal nobody is watching.
        return ["npx", "--yes", "repomix@latest"], True

    @staticmethod
    def _arguments(settings: RepoOptions) -> list[str]:
        """Translate tokenmill's repository options into Repomix's flags.

        Args:
            settings: The options to translate.

        Returns:
            The flags, without the launcher or the target.
        """
        argv = [
            "--stdout",
            "--style",
            "markdown",
            # Escaping, so a repository containing Markdown cannot break the
            # pack's own structure — which would also break the section parsing
            # the budget depends on.
            "--parsable-style",
            "--quiet",
            # Repomix scans for secrets by default. Left on deliberately: a
            # packing tool that helps a user paste their AWS keys into a model
            # is worse than one that is slightly slower.
            "--top-files-len",
            "0",
        ]
        if settings.include:
            argv += ["--include", ",".join(settings.include)]
        if settings.exclude:
            argv += ["--ignore", ",".join(settings.exclude)]
        if not settings.respect_gitignore:
            argv += ["--no-gitignore", "--no-default-patterns"]
        return argv


def _target(root: Path, backend_id: str) -> str:
    """Return the directory argument, refusing one that reads as an option.

    Args:
        root: The directory to pack.
        backend_id: Attributed on refusal.

    Returns:
        The path as a string.
    """
    return safe_path_argument(root, backend_id=backend_id)
