"""Peak memory, measured honestly or not reported at all.

There is no portable, correct "peak memory of this operation" for a Python
process that also spawns children, and pretending otherwise is the most quietly
wrong thing a benchmark can do. So this module measures two different things,
labels which is which, and reports ``None`` where it could measure neither.

**What each number is:**

* ``peak_python_kb`` — :mod:`tracemalloc`'s peak. **Exact** for Python objects
  and completely blind to everything else: a C library's own arena, the memory
  ``pdfplumber`` hands to Pillow, and every byte a child process uses. Portable.
* ``peak_rss_kb`` — the peak resident set of **this process and its
  descendants**, sampled during the run. This is the number that means something
  for a subprocess backend, and it is only available where the platform lets us
  sample it.
* ``baseline_rss_kb`` — the same figure read *once, immediately before* the
  block. Without it ``peak_rss_kb`` is close to uninterpretable in a matrix run:
  a Python process's resident set only grows, so by the fiftieth cell the peak
  is dominated by every library the previous forty-nine imported and the column
  reads as a slow climb rather than as a property of the backend. The difference
  between the two is what this cell actually added, and it is the difference
  that belongs in a report.

**Why sampling rather than :func:`resource.getrusage`.** ``ru_maxrss`` is a
high-water mark for the life of the process, not for an interval, so the
difference between two readings is not the peak of what happened between them —
it is zero whenever an earlier operation was larger. That is precisely wrong for
a matrix of cells run one after another, where the first heavy backend would
make every later cell report no memory at all. ``RUSAGE_CHILDREN`` has the same
shape across children.

So a background thread reads ``/proc`` every few milliseconds and keeps the
maximum. That has its own honest limitation, stated rather than hidden: a peak
that occurs *between* two samples is missed, so the figure is a lower bound.

**Where it does not work**, it says so. On anything without ``/proc`` — macOS,
Windows — ``peak_rss_kb`` is ``None`` and ``memory_method`` is
``"tracemalloc-only"``. A CI matrix that reported memory on one platform and
silently zero on two others would be worse than one that reports it on one.
"""

from __future__ import annotations

import os
import threading
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = ["MemoryReading", "measure_memory", "sampling_supported"]

#: How often to read ``/proc``. Fast enough to catch a conversion that allocates
#: for a few hundred milliseconds, slow enough that the sampler is not itself
#: a measurable cost: at 5 ms this is about 200 file reads per second.
_INTERVAL_S: Final = 0.005

#: Linux's per-process memory statistics.
_PROC: Final = Path("/proc")


def _page_kb() -> int:
    """Return the system page size in KiB, for ``statm``'s units.

    Returns:
        The page size, or 4 where the platform will not say — which is right on
        every architecture this project runs on and is only reached where
        ``/proc`` does not exist anyway, so the figure is unused there.
    """
    try:
        return int(os.sysconf("SC_PAGE_SIZE")) // 1024
    except (AttributeError, ValueError, OSError):  # pragma: no cover - non-POSIX
        return 4


#: Bytes per page, for ``statm``'s units. Read once.
_PAGE_KB: Final = _page_kb()


@dataclass(frozen=True, slots=True)
class MemoryReading:
    """What was measured, and how.

    Attributes:
        peak_python_kb: Peak Python allocations, from tracemalloc.
        peak_rss_kb: Peak resident set of this process and its descendants, or
            ``None`` where sampling is not available.
        baseline_rss_kb: The same figure just before the block, or ``None``.
            :attr:`added_rss_kb` is the pair's whole point.
        method: ``"proc-sampling"`` or ``"tracemalloc-only"``, so the number
            can be read correctly rather than trusted.
    """

    peak_python_kb: int | None
    peak_rss_kb: int | None
    method: str
    baseline_rss_kb: int | None = None

    @property
    def added_rss_kb(self) -> int | None:
        """How much resident memory this block added over what was already held.

        Returns:
            ``peak - baseline``, or ``None`` when either is unknown. Clamped at
            zero: a block that freed more than it allocated added nothing, and a
            negative "memory used" would be read as a measurement error rather
            than as the true answer.
        """
        if self.peak_rss_kb is None or self.baseline_rss_kb is None:
            return None
        return max(0, self.peak_rss_kb - self.baseline_rss_kb)


def sampling_supported() -> bool:
    """Whether the resident-set sampler can run on this platform.

    Returns:
        True on Linux, where ``/proc/<pid>/statm`` exists.
    """
    return (_PROC / "self" / "statm").exists()


class _Sampler:
    """Reads this process tree's resident set on a background thread."""

    def __init__(self) -> None:
        """Start with nothing sampled."""
        self.peak_kb = 0
        self.baseline_kb = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> _Sampler:
        """Begin sampling.

        Returns:
            Self, so the peak can be read after the block.
        """
        self.baseline_kb = _tree_rss_kb()
        self.peak_kb = self.baseline_kb
        self._thread = threading.Thread(target=self._run, name="tokenmill-rss", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        """Stop sampling and take one final reading.

        The final reading matters: a conversion that finished just before the
        last scheduled sample would otherwise have its peak missed entirely.
        """
        del exc
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self.peak_kb = max(self.peak_kb, _tree_rss_kb())

    def _run(self) -> None:
        """Sample until asked to stop."""
        while not self._stop.is_set():
            self.peak_kb = max(self.peak_kb, _tree_rss_kb())
            self._stop.wait(_INTERVAL_S)


def _tree_rss_kb() -> int:
    """Return the resident set of this process and its descendants, in KiB.

    Descendants are found through ``/proc/<pid>/task/*/children``, which lists
    only *direct* children — so this recurses. A backend that spawns a child
    that spawns a child (``npx`` running ``node``, which is the real case) is
    counted properly rather than reported as the launcher's own footprint.

    Returns:
        The total, or 0 where ``/proc`` is unavailable or the processes vanished
        mid-read. Zero rather than an exception: a memory sampler that could
        take down a benchmark run would be a worse trade than a missing figure.
    """
    total = 0
    seen: set[int] = set()
    frontier = [_pid_self()]
    while frontier:
        pid = frontier.pop()
        if pid in seen:
            continue
        seen.add(pid)
        total += _rss_kb(pid)
        frontier.extend(_children(pid))
    return total


def _pid_self() -> int:
    """Return this process's id.

    Returns:
        The pid.
    """
    return os.getpid()


def _rss_kb(pid: int) -> int:
    """Read one process's resident set.

    Args:
        pid: The process.

    Returns:
        Its resident set in KiB, or 0 when it has gone or cannot be read.
    """
    try:
        fields = (_PROC / str(pid) / "statm").read_text(encoding="ascii").split()
    except (OSError, ValueError):
        return 0
    # statm's second field is resident pages.
    try:
        return int(fields[1]) * _PAGE_KB
    except (IndexError, ValueError):  # pragma: no cover - a malformed statm
        return 0


def _children(pid: int) -> list[int]:
    """List one process's direct children.

    Args:
        pid: The parent.

    Returns:
        Their pids, empty when they cannot be read.
    """
    found: list[int] = []
    try:
        tasks = list((_PROC / str(pid) / "task").iterdir())
    except OSError:
        return found
    for task in tasks:
        try:
            raw = (task / "children").read_text(encoding="ascii")
        except OSError:
            continue
        found.extend(int(part) for part in raw.split() if part.isdigit())
    return found


class measure_memory:  # noqa: N801 - a context manager used as `with measure_memory() as m`
    """Measure peak memory across a block, both ways.

    Used as a context manager; read :attr:`reading` afterwards.

    ``tracemalloc`` is started and stopped around the block rather than left on,
    because it roughly doubles allocation cost and a benchmark that measured
    itself instrumented would report the wrong wall time. That means memory and
    timing come from **the same repeat but an instrumented one**, and the report
    says so: the published timing is the median of the uninstrumented repeats,
    and memory is from one extra pass.

    Attributes:
        reading: What was measured. Only meaningful after the block.
    """

    def __init__(self) -> None:
        """Prepare an empty measurement."""
        self.reading = MemoryReading(None, None, "none")
        self._sampler: _Sampler | None = None

    def __enter__(self) -> measure_memory:
        """Start both measurements.

        Returns:
            Self.
        """
        tracemalloc.start()
        if sampling_supported():
            self._sampler = _Sampler()
            self._sampler.__enter__()
        return self

    def __exit__(self, *exc: object) -> None:
        """Stop both measurements and record them."""
        del exc
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss: int | None = None
        baseline: int | None = None
        method = "tracemalloc-only"
        if self._sampler is not None:
            self._sampler.__exit__()
            rss = self._sampler.peak_kb or None
            baseline = self._sampler.baseline_kb or None
            method = "proc-sampling"
        self.reading = MemoryReading(
            peak_python_kb=peak // 1024,
            peak_rss_kb=rss,
            method=method,
            baseline_rss_kb=baseline,
        )
