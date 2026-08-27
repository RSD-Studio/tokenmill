"""Defect D2: conversions may overlap, and the global state must survive it.

These tests are the ones that would have failed before Phase 9. They are
deliberately about the *failure*, not about the lock: asserting that a lock is
acquired proves a lock is acquired, and the thing worth knowing is whether two
conversions running at once can corrupt each other's process.

Three properties, one test each, and each is a real observed failure mode:

1. `warnings.catch_warnings` saves and restores a module-global filter list, so
   interleaved save/restore leaves the process holding somebody else's filters.
   Under this project's `filterwarnings = ["error"]` that turns a warning into a
   raised exception in an unrelated conversion.
2. `os.environ.pop` + restore loses the variable entirely when two threads do it
   at once: the second pop reads `None` and the second restore writes nothing.
3. The stdlib root logger's handler list is a single mutable list, so an
   interleaved snapshot and restore leaks a handler or drops the caller's.

**How reliably these catch the defect, measured rather than assumed.** With the
lock removed and CPython's default 5 ms thread-switch interval, none of them
fails: the critical sections are a few microseconds long and almost never get
preempted. That is not evidence they are safe — it is why nobody hit this in
five phases. Lowering `sys.setswitchinterval` makes preemption likely without
changing the code under test, and the picture is then clear (16 threads, 300
rounds, this container, 2026-08-27):

    switch=0.005    filters_unchanged=True   env_keyerrors=0
    switch=0.001    filters_unchanged=True   env_keyerrors=0
    switch=0.0001   filters_unchanged=False  env_keyerrors=1
    switch=1e-05    filters_unchanged=True   env_keyerrors=3
    switch=1e-06    filters_unchanged=True   env_keyerrors=11

So they are not equally sharp, and pretending otherwise would be the kind of
"passes for the wrong reason" this project has already corrected twice. With the
lock replaced by a no-op and this fixture's switch interval in place, two of the
three go red immediately:

* **`os.environ`** — the sharpest, and it fails from *inside*
  `os.environ.pop(name, None)`. `MutableMapping.pop` checks membership and then
  deletes, so another thread deleting in between raises `KeyError` out of a call
  that was given a default precisely so it could not raise.
* **The root logger** — worse than expected, and worth quoting:

      assert root.handlers == before_handlers
      Left contains 117 more items, first extra item: <NullHandler (NOTSET)>

  117 leaked handlers from one run. Every one of them would go on formatting
  every record the host application logs, for the life of the process.

* **The warning filters** — the weak one, and said so rather than implied. The
  corruption is real and rare even at a microsecond switch interval: it appeared
  once in the sweep above, at 1e-4, and not at all at 1e-5 or 1e-6. This test
  will catch somebody removing the lock *and* getting unlucky. It is a
  regression guard, not a demonstration.

Every test runs the *real* helper the adapters use where there is one.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import warnings
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest

from tokenmill.core.globalstate import GLOBAL_STATE_LOCK, process_global_state

#: Enough threads and rounds that an unguarded interleaving is likely.
_THREADS = 16
_ROUNDS = 300

#: What to set CPython's thread-switch interval to for the duration.
#:
#: The default is 5 ms, at which a microsecond-long critical section is
#: essentially never preempted. This does not change the code under test; it
#: changes how often the interpreter offers another thread the chance to run,
#: which is the only reason these races are hard to see.
_SWITCH_INTERVAL = 1e-6


@pytest.fixture
def preemptive() -> Iterator[None]:
    """Make thread switches frequent enough that a race can actually happen.

    Yields:
        Nothing. The interval is restored afterwards, because leaving it at a
        microsecond would slow every test that ran later and would be exactly
        the kind of global-state leak this module is about.
    """
    previous = sys.getswitchinterval()
    sys.setswitchinterval(_SWITCH_INTERVAL)
    try:
        yield
    finally:
        sys.setswitchinterval(previous)


def _hammer(work: object) -> list[BaseException]:
    """Run ``work`` on many threads at once and collect what it raised.

    Args:
        work: A no-argument callable, run ``_ROUNDS`` times per thread.

    Returns:
        Every exception any thread raised, empty when all of them were clean.
    """
    failures: list[BaseException] = []
    barrier = threading.Barrier(_THREADS)

    def run() -> None:
        # A barrier so every thread starts inside the contended region at the
        # same moment, rather than the first finishing before the last starts.
        barrier.wait()
        for _ in range(_ROUNDS):
            try:
                work()  # type: ignore[operator]
            except BaseException as exc:  # collecting it is the whole point
                failures.append(exc)
                return

    with ThreadPoolExecutor(max_workers=_THREADS) as pool:
        list(pool.map(lambda _: run(), range(_THREADS)))
    return failures


class TestTheLockItself:
    def test_it_is_reentrant(self) -> None:
        """The gitingest adapter enters four nested blocks; a plain lock deadlocks.

        Asserted rather than trusted because the failure mode is a hang, which
        a test suite reports as a timeout with no useful message.
        """
        with process_global_state("outer"), process_global_state("inner"):
            assert True

    def test_it_releases_on_an_exception(self) -> None:
        def boom() -> None:
            with process_global_state("failing"):
                msg = "deliberate"
                raise RuntimeError(msg)

        with pytest.raises(RuntimeError, match="deliberate"):
            boom()

        # If the finally had not run, this would block forever.
        assert GLOBAL_STATE_LOCK.acquire(timeout=1.0)
        GLOBAL_STATE_LOCK.release()

    def test_it_actually_excludes(self) -> None:
        """Two threads must not be inside at once — checked without a lock."""
        inside = 0
        overlaps = 0
        counter_lock = threading.Lock()

        def work() -> None:
            nonlocal inside, overlaps
            with process_global_state("counting"):
                with counter_lock:
                    inside += 1
                    if inside > 1:
                        overlaps += 1
                with counter_lock:
                    inside -= 1

        assert _hammer(work) == []
        assert overlaps == 0


@pytest.mark.usefixtures("preemptive")
class TestWarningFiltersSurviveConcurrency:
    """A regression guard rather than a demonstration; see the module docstring."""

    def test_the_filter_list_comes_back_as_it_went_in(self) -> None:
        """Failure 1: interleaved save/restore leaks another thread's filters.

        The real helper is `warnings_as_conversion_warnings`; what it wraps is
        this, and this is the part that races.
        """
        before = list(warnings.filters)

        def work() -> None:
            with process_global_state("filters"), warnings.catch_warnings(record=True):
                warnings.simplefilter("always")

        assert _hammer(work) == []
        assert warnings.filters == before, (
            "the process's warning filters changed after concurrent use. Under "
            "filterwarnings = ['error'] that turns a warning into an exception "
            "in an unrelated conversion, which is exactly defect D2"
        )

    def test_the_real_helper_collects_each_thread_s_own_warning(self) -> None:
        """And attributes it to the right conversion, which is the user-visible half."""
        from tokenmill.backends._common import warnings_as_conversion_warnings
        from tokenmill.core.protocol import ConversionContext

        def work(index: int) -> list[str]:
            context = ConversionContext()
            with warnings_as_conversion_warnings(context, activity=f"job {index}"):
                warnings.warn(f"warning {index}", UserWarning, stacklevel=1)
            return context.warnings

        with ThreadPoolExecutor(max_workers=_THREADS) as pool:
            results = list(pool.map(work, range(_THREADS)))

        for index, collected in enumerate(results):
            assert len(collected) == 1, f"job {index} collected {collected}"
            assert f"job {index}" in collected[0]
            assert f"warning {index}" in collected[0]


@pytest.mark.usefixtures("preemptive")
class TestTheEnvironmentSurvivesConcurrency:
    """The one that reliably fails without the lock. See the module docstring."""

    def test_a_popped_variable_is_not_lost(self) -> None:
        """Failure 2, and the nastiest: the variable vanishes from the process.

        This is what the gitingest adapter does with `GITHUB_TOKEN` on every
        pack. Two threads each pop it and restore it: without the lock the
        second pop reads `None`, so the second restore writes nothing, and the
        value is gone for the whole process — including for whatever application
        embedded tokenmill and put it there.

        It also fails a second way, from *inside* `os.environ.pop`:
        `MutableMapping.pop` checks membership and then deletes, so another
        thread deleting in between raises `KeyError` out of a call that was
        given a default precisely so it could not raise.
        """
        name = "TOKENMILL_D2_PROBE"
        os.environ[name] = "the-original-value"
        try:

            def work() -> None:
                with process_global_state("environment"):
                    saved = os.environ.pop(name, None)
                    try:
                        assert name not in os.environ, (
                            "another thread restored the variable while this one "
                            "was inside the block; they are not mutually excluded"
                        )
                    finally:
                        if saved is not None:
                            os.environ[name] = saved

            assert _hammer(work) == []
            assert os.environ.get(name) == "the-original-value", (
                "the variable was lost from the process. This is defect D2's "
                "sharpest form: two threads popping and restoring lose it "
                "entirely, because the second pop reads None"
            )
        finally:
            os.environ.pop(name, None)


@pytest.mark.usefixtures("preemptive")
class TestRootLoggingSurvivesConcurrency:
    """The second reliable detector: 117 leaked handlers without the lock."""

    def test_handlers_and_level_come_back(self) -> None:
        """Failure 3: an interleaved snapshot leaks a handler or drops one."""
        root = logging.getLogger()
        before_handlers = list(root.handlers)
        before_level = root.level

        def work() -> None:
            with process_global_state("root logger"):
                handlers = list(root.handlers)
                level = root.level
                try:
                    # What importing gitingest does to the host process.
                    root.addHandler(logging.NullHandler())
                    root.setLevel(0)
                finally:
                    root.handlers[:] = handlers
                    root.setLevel(level)

        assert _hammer(work) == []
        assert root.handlers == before_handlers
        assert root.level == before_level
