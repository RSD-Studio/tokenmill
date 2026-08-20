"""Backend discovery and selection.

Backends are found through the ``tokenmill.backends`` entry point group. The
built-in backends register through exactly the same mechanism as a third-party
plugin — there is no special-casing, no hard-coded import list, and adding a
backend genuinely requires no edit to this module. That is the property Phase 1
exists to prove, and ``tests/unit/test_registry.py`` asserts it by registering a
backend that this package has never heard of.

Discovery is done once per :class:`Registry` and cached. Scanning entry points
means importing every backend module, which is the slow part of CLI start-up, so
it happens lazily on first use rather than at import time.

A plugin that fails to load does not take the process with it. Its exception is
caught, recorded, and surfaced as a backend whose availability is
:meth:`~tokenmill.core.models.Availability.broken`. A broken third-party plugin
must degrade to a greyed-out row, never a crash.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import Final

from tokenmill.core.errors import BackendUnavailable, UnsupportedFormat
from tokenmill.core.models import (
    Availability,
    BackendInfo,
    Domain,
    IsolationMode,
    LicenseTier,
    Source,
)
from tokenmill.core.protocol import Converter

__all__ = [
    "BACKEND_ENTRY_POINT_GROUP",
    "BrokenBackend",
    "Registry",
    "default_registry",
    "reset_default_registry",
]

#: The entry point group third-party plugins register under.
BACKEND_ENTRY_POINT_GROUP: Final = "tokenmill.backends"

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BrokenBackend:
    """A registered entry point that could not be loaded.

    Kept as data rather than discarded so the CLI can show the user *why* a
    backend they expected to see is missing. A plugin that raises on import is a
    bug in that plugin, and hiding it makes it undiagnosable.

    Attributes:
        id: The entry point name.
        error: The exception text from the failed load.
        source: Where the entry point came from, for the error message.
    """

    id: str
    error: str
    source: str

    @property
    def availability(self) -> Availability:
        """Return the availability this broken backend reports."""
        return Availability.broken(self.error)


class Registry:
    """Holds the backends available in this process.

    One instance is normally enough; :func:`default_registry` provides the
    process-wide one. Construct your own when you want an isolated set — the
    tests do exactly that to register a fake backend without touching the real
    entry points.
    """

    def __init__(self, entry_point_group: str = BACKEND_ENTRY_POINT_GROUP) -> None:
        """Initialise an empty registry.

        Discovery is deferred until the first lookup.

        Args:
            entry_point_group: The entry point group to scan.
        """
        self._group = entry_point_group
        self._converters: dict[str, Converter] = {}
        self._broken: dict[str, BrokenBackend] = {}
        self._loaded = False

    # -- discovery ---------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Scan entry points once, on first use."""
        if self._loaded:
            return
        self.load_from(entry_points(group=self._group))

    def load_from(self, eps: Iterable[EntryPoint]) -> None:
        """Load backends from an explicit set of entry points.

        Marks the registry as loaded, so the automatic scan will not run
        afterwards. This is how the tests inject a plugin — including a
        deliberately broken one — without installing a distribution.

        Args:
            eps: The entry points to load.
        """
        for ep in eps:
            self._load_one(ep)
        self._loaded = True

    def _load_one(self, ep: EntryPoint) -> None:
        """Load one entry point, recording rather than raising on failure.

        Args:
            ep: The entry point to load.
        """
        origin = getattr(ep, "value", ep.name)
        try:
            factory = ep.load()
            converter = factory() if callable(factory) else factory
            if not isinstance(converter, Converter):
                msg = (
                    f"{type(converter).__name__} does not implement the Converter "
                    f"protocol (needs info, is_available, supports, convert)"
                )
                raise TypeError(msg)
            info = converter.info
        except Exception as exc:
            # Any failure here is a third-party plugin's bug. Record it and keep
            # going: one bad plugin must not remove every other backend.
            _log.warning("backend plugin %r failed to load: %s", ep.name, exc)
            _log.debug("plugin load traceback", exc_info=True)
            self._broken[ep.name] = BrokenBackend(
                id=ep.name, error=f"{type(exc).__name__}: {exc}", source=origin
            )
            return

        self._verify_licence_policy(info)
        if info.id in self._converters:
            _log.warning("backend id %r registered twice; keeping the first (%s)", info.id, origin)
            return
        self._converters[info.id] = converter

    @staticmethod
    def _verify_licence_policy(info: BackendInfo) -> None:
        """Re-check the licence policy at registration time.

        :meth:`~tokenmill.core.models.BackendInfo.__post_init__` already refuses
        to build a violating descriptor, so this is belt and braces against a
        plugin that constructs its ``BackendInfo`` by some other route. Phase 7
        turns this into the full enforcement suite.

        Args:
            info: The backend's declared metadata.

        Raises:
            ValueError: If a non-permissive backend claims to run in-process.
        """
        if (
            info.license_tier is not LicenseTier.PERMISSIVE
            and info.isolation is IsolationMode.IN_PROCESS
        ):
            msg = (
                f"backend {info.id!r} is {info.license_tier.value} but declares "
                f"in-process isolation; refusing to register it"
            )
            raise ValueError(msg)

    def register(self, converter: Converter) -> None:
        """Add a backend directly, bypassing entry points.

        Intended for tests and for embedding tokenmill in a larger application.
        Plugins should use an entry point so that ``pip install`` is all a user
        needs to do.

        Args:
            converter: The backend to add.

        Raises:
            ValueError: If a backend with the same id is already registered.
        """
        self._verify_licence_policy(converter.info)
        if converter.info.id in self._converters:
            msg = f"a backend with id {converter.info.id!r} is already registered"
            raise ValueError(msg)
        self._converters[converter.info.id] = converter
        self._loaded = True

    # -- lookup ------------------------------------------------------------

    def __iter__(self) -> Iterator[Converter]:
        """Iterate over the loaded backends, ordered by id."""
        self._ensure_loaded()
        return iter([self._converters[k] for k in sorted(self._converters)])

    def __len__(self) -> int:
        """Return how many backends loaded successfully."""
        self._ensure_loaded()
        return len(self._converters)

    def __contains__(self, backend_id: object) -> bool:
        """Return whether a backend id is registered."""
        self._ensure_loaded()
        return backend_id in self._converters

    @property
    def broken(self) -> tuple[BrokenBackend, ...]:
        """Return the entry points that failed to load, ordered by id."""
        self._ensure_loaded()
        return tuple(self._broken[k] for k in sorted(self._broken))

    def ids(self) -> tuple[str, ...]:
        """Return every registered backend id, including broken ones."""
        self._ensure_loaded()
        return tuple(sorted({*self._converters, *self._broken}))

    def get(self, backend_id: str) -> Converter:
        """Return one backend by id.

        Args:
            backend_id: The id to look up.

        Returns:
            The backend.

        Raises:
            BackendUnavailable: If the id is unknown, or names a plugin that
                failed to load. A broken plugin is reported as unavailable with
                its load error, not as a missing one.
        """
        self._ensure_loaded()
        converter = self._converters.get(backend_id)
        if converter is not None:
            return converter
        broken = self._broken.get(backend_id)
        if broken is not None:
            raise BackendUnavailable(
                f"backend {backend_id!r} failed to load: {broken.error}",
                backend_id=backend_id,
                hint=broken.availability.hint,
            )
        raise BackendUnavailable(
            f"no backend named {backend_id!r}",
            backend_id=backend_id,
            hint=f"available backends: {', '.join(self.ids()) or 'none'}",
        )

    def for_domain(self, domain: Domain) -> tuple[Converter, ...]:
        """Return every backend serving a domain, best first.

        Args:
            domain: The domain to filter by.

        Returns:
            The matching backends in preference order.
        """
        return tuple(
            sorted(
                (c for c in self if domain in c.info.domains),
                key=_preference_key,
            )
        )

    def for_source(self, source: Source, *, available_only: bool = True) -> tuple[Converter, ...]:
        """Return every backend that claims a source, best first.

        Args:
            source: The input to match.
            available_only: Drop backends that cannot currently run.

        Returns:
            The candidate backends in preference order.
        """
        candidates = [c for c in self if c.supports(source)]
        if available_only:
            candidates = [c for c in candidates if c.is_available()]
        return tuple(sorted(candidates, key=_preference_key))

    def select(self, source: Source, *, backend_id: str | None = None) -> Converter:
        """Choose the backend to convert a source with.

        The preference order, in full, is:

        1. An explicitly requested ``backend_id`` always wins — if it cannot
           run, that is an error, not a reason to silently substitute
           something else. Silently converting with a different backend than
           the user asked for would make every measurement unattributable.
        2. Otherwise, among backends that claim the format and can run:
           highest :attr:`~tokenmill.core.models.BackendInfo.priority` first,
           then in-process before out-of-process (cheaper), then by id so the
           choice is deterministic rather than dependent on entry point order.

        Args:
            source: The input to convert.
            backend_id: Force a specific backend.

        Returns:
            The chosen backend.

        Raises:
            BackendUnavailable: If the named backend cannot run.
            UnsupportedFormat: If nothing available claims the source.
        """
        if backend_id is not None:
            converter = self.get(backend_id)
            availability = converter.is_available()
            if not availability:
                raise BackendUnavailable(
                    f"backend {backend_id!r} is not available: {availability.describe()}",
                    backend_id=backend_id,
                    hint=availability.hint,
                )
            return converter

        candidates = self.for_source(source)
        if candidates:
            return candidates[0]

        # Distinguish "nothing handles this" from "something does but it is not
        # installed" — those need different messages and different user actions.
        unavailable = self.for_source(source, available_only=False)
        if unavailable:
            names = ", ".join(c.info.id for c in unavailable)
            raise UnsupportedFormat(
                f"no available backend handles {source.format or 'this source'}",
                hint=f"these backends handle it but cannot run: {names}",
            )
        raise UnsupportedFormat(
            f"no backend handles {source.format or 'this source'}",
            hint=f"formats tokenmill can convert: {', '.join(self.known_formats()) or 'none'}",
        )

    def known_formats(self) -> tuple[str, ...]:
        """Return every input format any registered backend claims."""
        formats: set[str] = set()
        for converter in self:
            formats.update(converter.info.input_formats)
        return tuple(sorted(formats))


def _preference_key(converter: Converter) -> tuple[int, int, str]:
    """Return the sort key implementing the documented preference order.

    Args:
        converter: The backend to rank.

    Returns:
        A tuple ordering by descending priority, then in-process first, then id.
    """
    info = converter.info
    return (-info.priority, 0 if info.isolation is IsolationMode.IN_PROCESS else 1, info.id)


_DEFAULT: Registry | None = None


def default_registry() -> Registry:
    """Return the process-wide registry, building it on first call.

    Returns:
        The shared registry. Entry point discovery happens once per process.
    """
    global _DEFAULT  # one deliberate process-wide cache
    if _DEFAULT is None:
        _DEFAULT = Registry()
    return _DEFAULT


def reset_default_registry() -> None:
    """Discard the process-wide registry so the next call rebuilds it.

    Only useful in tests, where a plugin may be installed or removed part way
    through a session.
    """
    global _DEFAULT  # one deliberate process-wide cache
    _DEFAULT = None
