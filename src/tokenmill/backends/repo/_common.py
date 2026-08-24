"""Shared behaviour for the repository backends.

Three tools pack a repository into one file — gitingest in Python, Repomix in
Node, code2prompt in Rust — and they disagree about almost everything: which
files to include, how to mark a file boundary, whether to count tokens, and what
to do when the result is too big. This module is the set of behaviours tokenmill
makes identical across all three, so that a user sees one product with three
engines rather than three CLIs with a shared prefix.

Four things live here.

**Options** (:class:`RepoOptions`) — include and exclude globs, ``.gitignore``
respect, a maximum file size, binary skipping and a token budget, parsed once
from ``ConvertOptions.extra`` and translated into each tool's own flags by its
adapter.

**A working directory** (:func:`repo_workdir`) — a local path, either the one the
user gave or a fresh shallow clone of a Git URL. The clone is removed on every
exit path including failure, because a temp directory leaked on an error path is
a temp directory leaked on exactly the runs nobody is watching.

**Budget truncation** (:func:`apply_budget`) — one truncation strategy for all
three tools, in tokenmill's own tokenizer, reporting every file it dropped.

**A directory breakdown** (:func:`directory_totals`) — which folder is eating the
context.

---

**On counting tokens inside a backend.** ``docs/ARCHITECTURE.md`` says backends
convert and the pipeline measures, and that rule is not being bent here. A token
budget is an *input constraint on the conversion*, like the size limit: it
changes what the converter emits. The pipeline still does all the *reporting*
measurement, and a repository result carries no token counts of its own. The
line is: a backend may consult a tokenizer to obey a budget the user set; it may
never report a count.

**The budget's unit follows the tokenizer**, so ``--token-budget 5000
--tokenizer bytes`` caps at 5,000 UTF-8 bytes and ``--tokenizer o200k_base``
caps at 5,000 real tokens. That is why the flag is honest on a machine that
cannot download a vocabulary: the cap is real, and the CLI already says what
``bytes`` is not.

**When the tokenizer cannot load at all**, the budget cannot be enforced. It is
not silently ignored — the conversion warns that the budget did not apply and
emits everything, because a cap that quietly did nothing is worse than no cap.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final

from tokenmill.backends._common import render_markdown_table
from tokenmill.backends._subprocess import find_tool, run_tool, safe_path_argument
from tokenmill.core.errors import BackendFailed, CorruptSource, NetworkRequired
from tokenmill.core.models import ConvertOptions, Source, SourceKind
from tokenmill.core.protocol import ConversionContext

__all__ = [
    "DEFAULT_MAX_FILE_BYTES",
    "PackedFile",
    "RepoOptions",
    "TruncationReport",
    "apply_budget",
    "directory_totals",
    "full_pack",
    "matches_any",
    "note_repo_metadata",
    "read_repo_options",
    "render_truncation_note",
    "repo_workdir",
    "split_sections",
]

_log = logging.getLogger(__name__)

#: Files larger than this are skipped by default. Matches gitingest's own
#: default so that the three backends agree without anyone passing a flag.
DEFAULT_MAX_FILE_BYTES: Final = 10 * 1024 * 1024

#: The most dropped files the truncation note lists individually.
_NOTE_MAX_ROWS: Final = 20

#: Git URL schemes we will clone from. ``file://`` and ``ext::`` are absent
#: deliberately: ``ext::`` makes git execute an arbitrary command, which is a
#: remote-code-execution vector when the URL comes from anywhere but the user's
#: own keyboard, and a local repository should be given as a path.
_CLONE_SCHEMES: Final = ("https://", "http://", "git://", "ssh://")


@dataclass(frozen=True, slots=True)
class RepoOptions:
    """What varies between one repository packing and the next.

    Attributes:
        include: Glob patterns; when non-empty, only matching files are packed.
        exclude: Glob patterns to drop, applied after ``include``.
        respect_gitignore: Whether ``.gitignore`` rules are obeyed. On by
            default, and the reason ``tests/fixtures/sample_repo``'s
            ``secrets.env`` never reaches the output.
        skip_binary: Whether files that do not decode as text are skipped.
        max_file_bytes: Files larger than this are skipped.
        token_budget: Cap the packed output at this many tokens, in whatever
            unit the run's tokenizer counts. ``None`` means no cap.
        tree_tokens: Emit a per-directory breakdown alongside the pack.
        branch: Branch, tag or commit to check out when cloning a URL.
    """

    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    respect_gitignore: bool = True
    skip_binary: bool = True
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    token_budget: int | None = None
    tree_tokens: bool = False
    branch: str | None = None


def read_repo_options(options: ConvertOptions) -> RepoOptions:
    """Extract the repository settings from a conversion's ``extra`` mapping.

    Every value is read defensively and a wrong type falls back to the default
    rather than raising: ``extra`` is documented as backend-specific options
    that backends which do not understand them ignore, so a malformed entry must
    not be able to fail a conversion that would otherwise have worked.

    Args:
        options: The conversion options, whose ``extra`` carries these.

    Returns:
        The parsed settings.
    """
    extra: Mapping[str, Any] = options.extra
    return RepoOptions(
        include=_as_patterns(extra.get("include")),
        exclude=_as_patterns(extra.get("exclude")),
        respect_gitignore=_as_bool(extra.get("respect_gitignore"), default=True),
        skip_binary=_as_bool(extra.get("skip_binary"), default=True),
        max_file_bytes=_as_int(extra.get("max_file_bytes"), default=DEFAULT_MAX_FILE_BYTES),
        token_budget=_as_int_or_none(extra.get("token_budget")),
        tree_tokens=_as_bool(extra.get("tree_tokens"), default=False),
        branch=str(extra["branch"]) if extra.get("branch") else None,
    )


def _as_patterns(value: Any) -> tuple[str, ...]:
    """Coerce a glob-pattern option to a tuple of strings.

    Args:
        value: A comma-separated string, an iterable of strings, or ``None``.

    Returns:
        The patterns, empty when there are none.
    """
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    try:
        return tuple(str(item) for item in value)
    except TypeError:
        return ()


def _as_bool(value: Any, *, default: bool) -> bool:
    """Coerce an option to a boolean, falling back rather than raising.

    Args:
        value: The raw value.
        default: What to use when it is absent or unreadable.

    Returns:
        The boolean.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _as_int(value: Any, *, default: int) -> int:
    """Coerce an option to an int, falling back rather than raising.

    Args:
        value: The raw value.
        default: What to use when it is absent or unreadable.

    Returns:
        The integer.
    """
    parsed = _as_int_or_none(value)
    return parsed if parsed is not None else default


def _as_int_or_none(value: Any) -> int | None:
    """Coerce an option to an int, or ``None`` when it is absent or unreadable.

    Args:
        value: The raw value.

    Returns:
        The integer, or ``None``.
    """
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Working directory
# ---------------------------------------------------------------------------


@contextmanager
def repo_workdir(source: Source, options: ConvertOptions, backend_id: str) -> Iterator[Path]:
    """Yield a local directory holding the repository, cloning one if needed.

    A ``REPO`` source with a path is yielded as it is — nothing is copied, and
    the user's own working tree is never written to. A ``REPO`` source with a
    URL and no path is shallow-cloned into a temporary directory that is removed
    when the block ends, **including when the block raises**. That is the
    property the plan's risk register asks for by name, and it is a
    ``finally`` rather than a hopeful cleanup at the end of the happy path.

    All three repository backends go through this rather than using their own
    remote support, so that one clone policy, one set of options and one cleanup
    guarantee apply whichever engine the user picked.

    Args:
        source: The repository to work on.
        options: Supplies ``fetch`` and the timeout.
        backend_id: Attributed on failure.

    Yields:
        A directory that exists for the duration of the ``with`` block.

    Raises:
        CorruptSource: If the source is neither a directory nor a Git URL.
        NetworkRequired: If cloning is needed and fetching is switched off.
        BackendFailed: If ``git clone`` fails, or git is not installed.
    """
    if source.path is not None and source.path.is_dir():
        yield source.path
        return

    if source.kind is not SourceKind.REPO or not source.url:
        raise CorruptSource(
            f"{source.name} is not a repository: pass a directory or a Git URL",
            backend_id=backend_id,
            hint="repository backends take a local checkout or an https:// Git URL",
        )

    with _shallow_clone(source.url, options, backend_id) as checkout:
        yield checkout


@contextmanager
def _shallow_clone(url: str, options: ConvertOptions, backend_id: str) -> Iterator[Path]:
    """Clone a Git URL into a temporary directory, removing it afterwards.

    Args:
        url: The repository to clone.
        options: Supplies ``fetch``, the branch and the timeout.
        backend_id: Attributed on failure.

    Yields:
        The checkout directory.

    Raises:
        NetworkRequired: If fetching is switched off.
        BackendFailed: If the URL's scheme is refused, or the clone fails.
    """
    if not options.fetch:
        raise NetworkRequired(
            f"cloning {url} is disabled",
            backend_id=backend_id,
            hint="drop --offline to let tokenmill clone the repository you named",
        )
    if not url.startswith(_CLONE_SCHEMES):
        raise BackendFailed(
            f"refusing to clone {url!r}: only {', '.join(_CLONE_SCHEMES)} are allowed",
            backend_id=backend_id,
            hint="'ext::' URLs make git run an arbitrary command; pass a normal Git URL",
        )
    if find_tool("git") is None:
        raise BackendFailed(
            "git is not installed or not on PATH, so a remote repository cannot be cloned",
            backend_id=backend_id,
            hint="install git, or clone the repository yourself and pass the directory",
        )

    branch = _read_branch(options)
    directory = tempfile.mkdtemp(prefix="tokenmill-repo-")
    checkout = Path(directory) / "repo"
    try:
        argv = [
            "git",
            # `ext::` remote helpers run an arbitrary command. The scheme check
            # above already refuses them; this refuses them again at the layer
            # that would actually execute one, because a URL can become an
            # `ext::` one through a redirect in a repository's own config.
            "-c",
            "protocol.ext.allow=never",
            "-c",
            "core.askPass=",
            "clone",
            "--depth",
            "1",
            "--no-tags",
            # Submodules are a second network fetch and a second licence
            # surface, and nothing in Phase 4 needs them.
            "--recurse-submodules=no",
            "--quiet",
        ]
        if branch is not None:
            argv += ["--branch", branch]
        # `--` before the positional arguments, so neither the URL nor the
        # destination can be read as an option however they are spelled.
        argv += ["--", url, safe_path_argument(checkout, backend_id=backend_id)]

        # A prompt would hang forever holding a terminal nobody is watching.
        os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")
        run_tool(argv, backend_id=backend_id, timeout_s=options.timeout_s)
        yield checkout
    finally:
        # Every exit path, including an exception raised inside the `with` block
        # this context manager wraps.
        shutil.rmtree(directory, ignore_errors=True)


def _read_branch(options: ConvertOptions) -> str | None:
    """Return the branch to clone, refusing one that could be read as an option.

    Args:
        options: Supplies ``extra["branch"]``.

    Returns:
        The branch name, or ``None``.
    """
    branch = options.extra.get("branch")
    if not branch:
        return None
    text = str(branch)
    return None if text.startswith("-") else text


# ---------------------------------------------------------------------------
# Parsing a packed file back into its parts
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PackedFile:
    """One file's section inside a packed repository.

    Attributes:
        path: The repository-relative path, as the tool wrote it.
        text: The whole section, header included, so that re-joining the
            sections reproduces the pack.
    """

    path: str
    text: str


#: How each tool marks a file boundary, discovered by running it and reading the
#: output rather than from documentation. Each is anchored to the start of a
#: line so a matching string *inside* a file cannot be mistaken for a header.
_SECTION_PATTERNS: Final[Mapping[str, re.Pattern[str]]] = {
    # gitingest: a rule of '=' characters, FILE: <path>, another rule.
    "gitingest": re.compile(r"^=+\nFILE: (?P<path>.+)\n=+\n", re.MULTILINE),
    # Repomix --style markdown: '## File: <path>'.
    "repomix": re.compile(r"^## File: (?P<path>.+)$\n", re.MULTILINE),
    # code2prompt markdown: a backtick-quoted path followed by a colon, then a
    # fenced block. Not '## File:' — that was a guess, and running it produced
    # the adapter's "format was not recognised" warning rather than a silent
    # file count of zero, which is the behaviour that warning exists for.
    "code2prompt": re.compile(r"^`(?P<path>[^`\n]+)`:$\n", re.MULTILINE),
}


def split_sections(text: str, tool: str) -> tuple[str, list[PackedFile]]:
    """Split a packed repository into its preamble and its per-file sections.

    The preamble is everything before the first file — the summary and the
    directory tree — and it is kept whole, because a pack without its tree is
    much harder to read and it is small.

    Args:
        text: The tool's whole output.
        tool: Which tool produced it, selecting the header pattern.

    Returns:
        The preamble, and the file sections in the order they appeared. When no
        header matches, the whole text is the preamble and there are no
        sections — which is the honest answer to "this tool's format changed",
        and callers must treat it as "the budget could not be applied" rather
        than as "there are no files".
    """
    pattern = _SECTION_PATTERNS.get(tool)
    if pattern is None:  # pragma: no cover - guarded by the adapters
        return text, []

    matches = list(pattern.finditer(text))
    if not matches:
        return text, []

    preamble = text[: matches[0].start()]
    sections: list[PackedFile] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append(
            PackedFile(path=match.group("path").strip(), text=text[match.start() : end])
        )
    return preamble, sections


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TruncationReport:
    """What a budget actually did.

    Attributes:
        applied: Whether the budget was enforced at all. False when no budget
            was set, or when no tokenizer could be loaded to measure against.
        budget: The cap that was asked for.
        kept: Paths that made it into the output.
        dropped: Paths that did not, each with what it would have cost.
        total: What the whole pack would have cost.
        emitted: What the emitted document costs, truncation note included.
        unit: The tokenizer id the counts are in.
        over_budget: Whether the emitted document exceeds the budget anyway.
            True only when the directory tree alone is bigger than the cap; the
            tree is never dropped, so the overrun is reported rather than
            hidden.
    """

    applied: bool
    budget: int | None
    kept: tuple[str, ...] = ()
    dropped: tuple[tuple[str, int], ...] = ()
    total: int = 0
    emitted: int = 0
    unit: str = ""
    over_budget: bool = False

    @property
    def dropped_count(self) -> int:
        """Return how many files were dropped."""
        return len(self.dropped)


def render_truncation_note(report: TruncationReport, *, compact: bool = False) -> str:
    """Render the note appended to a truncated pack.

    A truncation that left no trace in the document would be invisible to
    whatever reads it next — which, for this project's output, is a language
    model that cannot ask. The note goes in the text itself as well as in the
    warnings and the metadata, because the text is the part that travels.

    Args:
        report: What the budget did.
        compact: Emit a single line instead of the table. Used when the table
            would not fit the budget, so that the *content* never has to shrink
            to make room for the explanation. The full list is in the result's
            metadata either way, so nothing is lost by shortening the prose.

    Returns:
        The note, or an empty string when nothing was dropped.
    """
    if not report.dropped:
        return ""
    if compact:
        return (
            f"\n\n> Truncated to fit a {report.budget:,}-{report.unit} budget: "
            f"{report.dropped_count:,} file(s) omitted. The full list is in this "
            f"conversion's `dropped_files` metadata.\n"
        )
    lines = [
        "",
        "---",
        "",
        f"## Truncated to fit a {report.budget:,}-{report.unit} budget",
        "",
        f"{report.dropped_count} file(s) were omitted, costing "
        f"{report.total - report.emitted:,} {report.unit} of the "
        f"{report.total:,} the full pack would have needed.",
        "",
    ]
    # Bounded: on a repository with a thousand dropped files the list would be
    # larger than the pack it is apologising for, and it competes with the
    # content for the same budget.
    listed = report.dropped[:_NOTE_MAX_ROWS]
    rows: list[list[str]] = [["path", report.unit]]
    rows.extend([path, f"{cost:,}"] for path, cost in listed)
    lines.append(render_markdown_table(rows))
    if len(report.dropped) > len(listed):
        lines.append("")
        lines.append(f"...and {len(report.dropped) - len(listed):,} more.")
    lines.append("")
    lines.append(
        "The complete list is in this conversion's `dropped_files` metadata "
        "(`--json`), so nothing is only in prose."
    )
    return "\n".join(lines)


def full_pack(preamble: str, sections: Sequence[PackedFile]) -> str:
    """Reassemble a pack from its preamble and sections.

    Named because two callers need exactly the same assembly and must not
    disagree about it: :func:`apply_budget` measures it against the budget, and
    a backend records it as the ``packed`` stage so that what the budget removed
    is visible in ``--show-stages``.

    Args:
        preamble: The summary and directory tree.
        sections: The per-file sections, in the tool's order.

    Returns:
        The untruncated pack.
    """
    return preamble + "".join(section.text for section in sections)


def apply_budget(
    preamble: str,
    sections: Sequence[PackedFile],
    *,
    budget: int | None,
    count: Callable[[str], int] | None,
    unit: str,
) -> tuple[str, TruncationReport]:
    """Trim a packed repository to fit a token budget, whole files at a time.

    **The documented truncation strategy**, in three rules:

    1. **The preamble is always kept.** The summary and the directory tree are
       what tell a reader that files are missing and which ones. Dropping them
       to save room would remove the only evidence that truncation happened.
    2. **Files are kept in the order the tool emitted them**, until the next one
       would not fit. Every tool here orders its output deliberately — Repomix
       by git change frequency, gitingest by walk order — and re-sorting would
       substitute tokenmill's judgement for the one the user chose a backend
       for.
    3. **A file is never partially included.** Half a Python module is worse
       than no Python module: a model cannot tell that the rest was cut, and
       will happily reason about a class whose methods have vanished. Whole
       files only.

    A file that would not fit does not stop the walk — a later, smaller file may
    still fit. That keeps a single enormous file from wasting the whole budget.

    Args:
        preamble: The summary and tree, always kept.
        sections: The per-file sections, in the tool's order.
        budget: The cap, or ``None`` for no cap.
        count: Counts one string in the run's tokenizer, or ``None`` when no
            tokenizer could be loaded.
        unit: The tokenizer id, for the report.

    Returns:
        The possibly-truncated text and a report of what happened. When the
        budget is ``None`` or ``count`` is ``None``, the text is unchanged and
        the report says the budget was not applied — never silently.
    """
    joined = full_pack(preamble, sections)
    if budget is None or count is None:
        return joined, TruncationReport(applied=False, budget=budget, unit=unit)

    total = count(joined)
    if total <= budget:
        return joined, TruncationReport(
            applied=True,
            budget=budget,
            kept=tuple(section.path for section in sections),
            total=total,
            emitted=total,
            unit=unit,
        )

    costs = [(section, count(section.text)) for section in sections]
    preamble_cost = count(preamble)

    def keep(eligible: set[int]) -> tuple[str, list[str], list[tuple[str, int]], list[int], int]:
        """Pack the eligible sections that still fit, in the tool's own order.

        Args:
            eligible: Indices into ``costs`` that are allowed to be included.

        Returns:
            The assembled text, the kept paths, the dropped paths with their
            costs, the kept indices, and what the text costs.
        """
        chunks: list[str] = [preamble]
        kept: list[str] = []
        kept_indices: list[int] = []
        dropped: list[tuple[str, int]] = []
        used = preamble_cost
        for index, (section, cost) in enumerate(costs):
            if index in eligible and used + cost <= budget:
                chunks.append(section.text)
                kept.append(section.path)
                kept_indices.append(index)
                used += cost
            else:
                dropped.append((section.path, cost))
        return "".join(chunks), kept, dropped, kept_indices, used

    def describe(kept: list[str], dropped: list[tuple[str, int]], used: int) -> TruncationReport:
        """Build the report for one candidate split.

        Args:
            kept: Paths that made it in.
            dropped: Paths that did not, with what they would have cost.
            used: What the kept text costs.

        Returns:
            The report, before the note's own cost is added.
        """
        return TruncationReport(
            applied=True,
            budget=budget,
            kept=tuple(kept),
            dropped=tuple(dropped),
            total=total,
            emitted=used,
            unit=unit,
        )

    eligible = set(range(len(costs)))
    text, kept, dropped, indices, used = keep(eligible)
    if not dropped:  # pragma: no cover - `total <= budget` already returned above
        return text, describe(kept, dropped, used)

    # The truncation note is part of the output, so it counts against the
    # budget. **The note degrades before the content does**: a file that fits is
    # never evicted to make room for a longer explanation of the files that did
    # not. The full table is used when it fits and a one-line note when it does
    # not — the complete list is in the result's metadata either way, so
    # shortening the prose loses nothing.
    #
    # Two earlier versions got this wrong in opposite directions and both are
    # worth remembering. The first appended the note after the budget was
    # computed and emitted 1,482 bytes against a 1,200-byte cap — a cap exceeded
    # by the explanation of the cap. The second dropped files to make room, and
    # since each drop adds a row to the note it emptied the pack chasing a note
    # that grew faster than the content shrank.
    report = describe(kept, dropped, used)
    full = render_truncation_note(report)
    if used + count(full) <= budget:
        return text + full, replace(report, emitted=used + count(full))

    # The compact note is a fixed size, so dropping a file strictly reduces the
    # document and this terminates. `greedy` is kept as the fallback: if no
    # split fits, the one with the most content in it is the useful answer, and
    # dropping files that cannot help is pure loss.
    greedy: tuple[str, TruncationReport] | None = None
    while True:
        report = describe(kept, dropped, used)
        compact = render_truncation_note(report, compact=True)
        emitted = used + count(compact)
        candidate = (text + compact, replace(report, emitted=emitted))
        if greedy is None:
            greedy = candidate
        if emitted <= budget:
            return candidate
        if not indices:
            # Even with nothing kept it does not fit: the directory tree alone
            # is over budget. It is never dropped, because it is the only thing
            # telling a reader which files are missing, so report the overrun.
            return greedy[0], replace(greedy[1], over_budget=True)
        eligible.discard(indices[-1])
        text, kept, dropped, indices, used = keep(eligible)


# ---------------------------------------------------------------------------
# Per-directory breakdown
# ---------------------------------------------------------------------------


def directory_totals(
    sections: Sequence[PackedFile], *, count: Callable[[str], int], unit: str
) -> str:
    """Render "which folder is eating my context" as a Markdown table.

    Every directory on each file's path is credited, so a nested tree rolls up:
    a file at ``src/widgetlib/core.py`` counts towards ``src`` and towards
    ``src/widgetlib``. That is what makes the table answer the question a user
    actually asks, which is about a subtree rather than about a single level.

    Args:
        sections: The per-file sections.
        count: Counts one string in the run's tokenizer.
        unit: The tokenizer id, for the header.

    Returns:
        The table, or an empty string when there is nothing to report.
    """
    if not sections:
        return ""

    totals: dict[str, int] = {}
    files: dict[str, int] = {}
    grand = 0
    for section in sections:
        cost = count(section.text)
        grand += cost
        for directory in _ancestors(section.path):
            totals[directory] = totals.get(directory, 0) + cost
            files[directory] = files.get(directory, 0) + 1

    if grand <= 0:
        return ""

    ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    rows: list[list[str]] = [["directory", unit, "share", "files"]]
    rows.extend(
        [directory, f"{cost:,}", f"{cost / grand:.1%}", str(files[directory])]
        for directory, cost in ordered
    )
    return render_markdown_table(rows)


def _ancestors(path: str) -> list[str]:
    """Return every directory a file belongs to, outermost first.

    Args:
        path: A repository-relative file path.

    Returns:
        The directories, using ``.`` for a file at the repository root so that
        top-level files are still credited somewhere rather than vanishing from
        the breakdown.
    """
    parts = _path_directories(path)
    if not parts:
        return ["."]
    return ["/".join(parts[: index + 1]) for index in range(len(parts))]


def _path_directories(path: str) -> list[str]:
    """Split a packed file's path into its directory components.

    Written by hand rather than with :mod:`pathlib` because these paths come
    from three external tools and may use either separator regardless of the
    platform tokenmill is running on. ``pathlib`` would treat a backslash as an
    ordinary character on Linux and as a separator on Windows, which would make
    the breakdown depend on the operating system rather than on the repository.

    Args:
        path: A repository-relative file path.

    Returns:
        The directory components, without the file name.
    """
    normalised = path.replace("\\", "/").strip("/")
    parts = [part for part in normalised.split("/") if part and part != "."]
    return parts[:-1]


def matches_any(path: str, patterns: Sequence[str]) -> bool:
    """Report whether a path matches any of a set of glob patterns.

    Args:
        path: A repository-relative path.
        patterns: Glob patterns.

    Returns:
        True when at least one matches. Matching is attempted against the whole
        path and against the bare file name, so ``*.py`` behaves the way a user
        expects on a nested file rather than only at the root.
    """
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return any(
        fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(name, pattern) for pattern in patterns
    )


def note_repo_metadata(
    context: ConversionContext,
    *,
    root: Path,
    tool: str,
    sections: Sequence[PackedFile],
    report: TruncationReport,
    full_text: str | None = None,
) -> None:
    """Record the structured facts every repository conversion should carry.

    Args:
        context: Collects the notes.
        root: The directory that was packed.
        tool: Which engine produced the pack.
        sections: The per-file sections that were parsed out of it.
        report: What the budget did.
        full_text: The pack before the budget truncated it. Recorded as a
            ``packed`` stage **only when files were actually dropped**, so that
            budget truncation appears as a row in ``--show-stages`` rather than
            only in a warning (defect D8). Passing it unconditionally would put
            a second copy of every pack in memory to report a saving of zero.
    """
    if full_text is not None and report.dropped:
        context.stage("packed", full_text)
    context.note("repository", root.name)
    context.note("pack_tool", tool)
    context.note("file_count", len(sections))
    context.note("budget_applied", report.applied)
    if report.budget is not None:
        context.note("token_budget", report.budget)
    if report.dropped:
        context.note("dropped_file_count", report.dropped_count)
        context.note("dropped_files", [path for path, _ in report.dropped])
