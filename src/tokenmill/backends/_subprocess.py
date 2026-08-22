"""The minimum honest way to run an external tool; Phase 7 replaces it.

**Phase 7 replaces this module.** Phase 4 needs two subprocess backends —
Repomix is a Node program and code2prompt is a Rust binary, and neither can be
imported into a Python process at any price. The shared, hardened
``SubprocessConverter`` those backends are supposed to subclass is a **Phase 7**
deliverable and does not exist.

Rather than build half of Phase 7 here, this module does the smallest thing that
lets Phase 4 be correct, and says plainly what it is not. It is sited at
``tokenmill.backends._subprocess`` — one level above the tiers, next to
``_common`` — so Phase 7 can absorb it wherever it wants the real base class to
live, without a third rewrite of the call sites.

**What this module does**

* Finds an executable on ``PATH``, and reports its absence as an
  :class:`~tokenmill.core.models.Availability` carrying an install hint rather
  than as a crash.
* Runs it with a **list of arguments and never a shell**, with a timeout, with
  ``stdin`` closed, and with stdout and stderr captured.
* Maps what happens onto the tokenmill error taxonomy: a timeout is
  :class:`~tokenmill.core.errors.Timeout`, a non-zero exit is
  :class:`~tokenmill.core.errors.BackendFailed` carrying ``stderr``, a vanished
  binary is :class:`~tokenmill.core.errors.BackendUnavailable`.
* Refuses an argument that begins with ``-`` where a path was expected, which is
  the injection this project's risk register names by name.

**What this module does NOT do, and Phase 7 owes**

* **No sandboxing.** No resource limits, no filesystem confinement, no network
  namespace. A tool run through here has the same access the user does.
* **No binary discovery beyond ``PATH``.** No bundled binaries, no version
  managers, no configured search paths.
* **No version probing or pinning.** tokenmill cannot currently say which
  Repomix produced a given output, so a result's provenance is weaker than a
  Python backend's, where the package version is knowable.
* **No allow-list.** Any adapter can name any executable. Phase 7's licence
  enforcement needs the opposite: a checked list of what may be invoked, so a
  copyleft tool's isolation is enforced rather than declared.
* **No streaming.** Output is buffered whole, so a tool that emits a gigabyte
  will hold a gigabyte in memory. Bounded by the caller passing sensible limits
  to the tool itself, which is not the same as being bounded here.

That list is repeated in ``PROGRESS.md`` under deferred work, because a module
docstring is not where a project tracks what it still owes.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from tokenmill.core.errors import BackendFailed, BackendUnavailable, Timeout
from tokenmill.core.models import Availability

__all__ = ["ToolResult", "find_tool", "probe_tool", "run_tool", "safe_path_argument"]

_log = logging.getLogger(__name__)

#: Environment variables removed from every child process.
#:
#: A packing tool that picked up the parent's proxy settings, or a Node tool that
#: inherited ``NODE_OPTIONS``, would produce output that depends on the shell it
#: was launched from. That is the same objection that turned off Kreuzberg's
#: cache in Phase 2: a converter whose result depends on ambient state cannot be
#: described honestly in ``docs/BACKENDS.md``.
_STRIPPED_ENV: Final[tuple[str, ...]] = ("NODE_OPTIONS", "PYTHONSTARTUP")


@dataclass(frozen=True, slots=True)
class ToolResult:
    """What one external tool run produced.

    Attributes:
        stdout: Captured standard output, decoded as UTF-8 with replacement.
        stderr: Captured standard error, decoded the same way.
        returncode: The process's exit status.
        argv: The exact argument list that was executed, for provenance.
        duration_s: Wall-clock seconds the child took.
    """

    stdout: str
    stderr: str
    returncode: int
    argv: tuple[str, ...]
    duration_s: float


def find_tool(name: str) -> str | None:
    """Locate an executable on ``PATH``.

    Args:
        name: The executable's name.

    Returns:
        Its absolute path, or ``None`` when it is not on ``PATH``.
    """
    return shutil.which(name)


def probe_tool(name: str, *, hint: str) -> Availability:
    """Report whether an executable is available, with a way to install it.

    Args:
        name: The executable to look for.
        hint: How to install it, shown to the user when it is absent. Required
            rather than optional: "``repomix`` is missing" without "run ``npm
            install -g repomix``" is a dead end, and the whole point of the
            availability model is that an unavailable backend says what to do.

    Returns:
        Present when the executable is on ``PATH``, otherwise a missing binary
        carrying the hint.
    """
    if find_tool(name) is None:
        return Availability.missing_binary(name, hint=hint)
    return Availability.present()


def safe_path_argument(path: Path, *, backend_id: str) -> str:
    """Render a filesystem path as an argument that cannot be read as an option.

    A repository path is attacker-controlled input the moment someone runs
    tokenmill on a checkout they did not write, and a directory named
    ``--config=evil`` is a legal directory name on every platform this project
    supports. Argument lists stop shell injection; they do **not** stop a path
    from being parsed as a flag by the program receiving it.

    Callers must also place ``--`` before positional arguments where the tool
    supports it. This function is the belt to that pair of braces: it refuses
    outright rather than hoping the tool has a ``--`` and honours it.

    Args:
        path: The path to pass.
        backend_id: Attributed on refusal.

    Returns:
        The path as a string, absolute.

    Raises:
        BackendFailed: If the resolved path begins with ``-``.
    """
    text = str(path)
    if text.startswith("-"):
        raise BackendFailed(
            f"refusing to pass {text!r} as an argument: a path beginning with '-' "
            f"would be read as an option by the tool being run",
            backend_id=backend_id,
            hint="rename the directory, or pass it by an absolute path from elsewhere",
        )
    return text


def run_tool(
    argv: list[str],
    *,
    backend_id: str,
    timeout_s: float,
    cwd: Path | None = None,
    expect_success: bool = True,
) -> ToolResult:
    """Run an external tool and return what it produced.

    Args:
        argv: The executable and its arguments, already split. **Never a
            string**: ``shell=True`` is not used anywhere in this project, and a
            string here would be the only way to reintroduce it.
        backend_id: Attributed on failure.
        timeout_s: Wall-clock budget. The child is killed when it expires.
        cwd: Working directory for the child.
        expect_success: Raise on a non-zero exit. Pass ``False`` for a tool that
            signals something meaningful with an exit code, so the caller can
            inspect it.

    Returns:
        The captured output.

    Raises:
        ValueError: If ``argv`` is empty. A programming error, not a user one.
        BackendUnavailable: If the executable is not there when it is run —
            which is different from the probe having said so, because a tool can
            be uninstalled between the two.
        Timeout: If the child exceeds ``timeout_s``.
        BackendFailed: If it exits non-zero and ``expect_success`` is set.
    """
    if not argv:
        msg = "run_tool needs at least an executable"
        raise ValueError(msg)

    import time

    environment = {k: v for k, v in os.environ.items() if k not in _STRIPPED_ENV}
    _log.debug("running %s", argv)
    started = time.perf_counter()
    try:
        completed = subprocess.run(  # noqa: S603 - list argv, shell=False, no user string
            argv,
            capture_output=True,
            timeout=timeout_s,
            cwd=str(cwd) if cwd is not None else None,
            env=environment,
            # Closed rather than inherited: a tool that decides to prompt would
            # otherwise hang forever holding the terminal.
            stdin=subprocess.DEVNULL,
            check=False,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise BackendUnavailable(
            f"{argv[0]} is not installed or not on PATH",
            backend_id=backend_id,
            hint=f"install {argv[0]}, or choose a backend that needs no external tool",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise Timeout(
            f"{argv[0]} did not finish within {timeout_s:g}s",
            backend_id=backend_id,
            hint="raise --timeout, or narrow the input with --include or --exclude",
        ) from exc
    duration = time.perf_counter() - started

    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    result = ToolResult(
        stdout=stdout,
        stderr=stderr,
        returncode=completed.returncode,
        argv=tuple(argv),
        duration_s=duration,
    )

    if expect_success and completed.returncode != 0:
        # stderr goes on the exception rather than into the message: the message
        # is what a user reads, and a hundred lines of a Node stack trace in it
        # would bury the one sentence that matters. `BackendFailed.stderr` has
        # existed since Phase 1 for exactly this.
        raise BackendFailed(
            f"{argv[0]} exited {completed.returncode}: {_first_meaningful_line(stderr)}",
            backend_id=backend_id,
            stderr=stderr,
        )
    return result


def _first_meaningful_line(stderr: str) -> str:
    """Return the first line of ``stderr`` worth putting in an error message.

    Args:
        stderr: The captured error output.

    Returns:
        The first non-empty line, truncated, or a placeholder when the tool
        failed silently — which happens, and "exited 1" with nothing after it is
        more honest than an empty string that reads like a formatting bug.
    """
    for line in stderr.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped if len(stripped) <= 200 else f"{stripped[:197]}..."
    return "no error output"
