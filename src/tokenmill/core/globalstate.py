"""The one lock that makes concurrent conversions safe, and why it exists.

**Defect D2.** Several third-party libraries this project wraps can only be made
to behave by reaching for process-global state — the warnings filter list, the
root logger's handlers, an environment variable, loguru's activation registry.
Every one of those is a single mutable thing shared by the whole interpreter,
every use here saves it, changes it and puts it back, and **none of that is
safe when two conversions overlap**.

The failure is not theoretical and it is worth spelling out, because "not
thread-safe" understates it. Take :func:`warnings.catch_warnings`, which saves
and restores a module-global filter list::

    thread A: save filters []          thread B: -
    thread A: install "always"         thread B: save filters ["always"]   <-- A's
    thread A: restore []               thread B: install "ignore ..."
    thread A: (converting, no filter)  thread B: restore ["always"]        <-- A's
                                                                            leaked

A leaves the process holding B's filters, or B leaves it holding A's. Under this
project's ``filterwarnings = ["error"]`` that turns a warning which should have
reached the user as a :class:`~tokenmill.core.errors.ConversionError`-free
warning into a raised exception in **an unrelated conversion**, or the reverse.
``os.environ`` is worse rather than better: two threads that each pop
``GITHUB_TOKEN`` and restore it lose the token from the process entirely,
because the second pop reads ``None`` and the second restore writes nothing.

Phase 8 responded by running the batch queue on **one** worker thread, which was
correct and cost a feature: batch throughput was bounded by a defect rather than
by the work.

**What this module does instead.** One process-wide reentrant lock, held across
every block that touches global state, so those blocks are atomic with respect
to each other. The lock is reentrant because the blocks nest — the gitingest
adapter holds four of them at once — and a plain lock would deadlock on the
second.

**What makes that worth having is where the blocks are, not the lock itself.**
A lock around a whole conversion would serialise everything and change nothing.
So the sites were narrowed first, and the result is uneven in a way worth
knowing before reading a benchmark:

===============================  ==================  =========================
Site                             What it covers      Effect on a parallel run
===============================  ==================  =========================
``markitdown`` / ``crawl4ai``    the **import**      Negligible. After the
warning capture                  only               first conversion an import
                                                    is a ``sys.modules``
                                                    lookup.
``compress`` import              the **import**      Negligible, same reason.
                                 only
``docling`` deprecation filter   the whole           Docling conversions
                                 conversion          serialise against each
                                                    other.
``gitingest`` (four blocks)      the whole ingest    gitingest conversions
                                                    serialise against each
                                                    other.
===============================  ==================  =========================

So **pdfplumber, pypdf, plaintext, trafilatura, readability, markdownify_html,
markitdown, kreuzberg, and every subprocess backend** — pandoc, LibreOffice,
PyMuPDF4LLM, repomix, code2prompt — run fully in parallel. Docling and gitingest
do not. That is a real limitation and it is the honest shape of the fix, rather
than a claim that D2 has been made to vanish.

**What this is not.** It is not a general-purpose "tokenmill is thread-safe"
guarantee. It protects the specific global state the adapters in *this*
repository touch. A third-party backend that calls
:func:`warnings.catch_warnings` on its own, without going through
:func:`tokenmill.backends._common.warnings_as_conversion_warnings`, is outside
it — which is why that helper exists and why ``docs/ADDING_A_BACKEND.md`` tells
authors to use it.

It is also not a substitute for a process pool, which would sidestep all of this
by not sharing an interpreter. `docs/ARCHITECTURE.md` records why one is not
used: a `ConversionResult` carries the whole converted document across a pickle
boundary, and several backends already spawn their own children.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final

__all__ = ["GLOBAL_STATE_LOCK", "process_global_state"]

_log = logging.getLogger(__name__)

#: The single lock every global-state block acquires.
#:
#: Reentrant, because the blocks nest: the gitingest adapter enters four of them
#: at once and a plain :class:`threading.Lock` would deadlock on the second.
#:
#: One lock rather than one per kind of state, deliberately. Four locks acquired
#: in different orders by different adapters is a deadlock waiting for the day
#: somebody adds the fifth, and the contention this saves is not worth that: the
#: blocks are either microseconds long or belong to a backend that is slow for
#: other reasons.
GLOBAL_STATE_LOCK: Final = threading.RLock()


@contextmanager
def process_global_state(activity: str) -> Iterator[None]:
    """Serialise a block that reads or writes process-global state.

    Args:
        activity: What is being done, for the debug log. Named rather than
            anonymous because the one question worth asking of a slow parallel
            run is *which* block everything is queueing behind, and a log line
            answers it without a profiler.

    Yields:
        Nothing; the lock is held for the duration of the block.
    """
    # A contended acquire is worth seeing, and an uncontended one costs an
    # attribute lookup. `acquire(blocking=False)` first so the log line is only
    # written when there really was somebody else inside.
    if not GLOBAL_STATE_LOCK.acquire(blocking=False):
        _log.debug("waiting for the process-global lock to enter %s", activity)
        GLOBAL_STATE_LOCK.acquire()
    try:
        yield
    finally:
        GLOBAL_STATE_LOCK.release()
