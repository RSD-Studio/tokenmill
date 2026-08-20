"""Registry discovery, availability degradation and backend selection.

The headline test here is
:meth:`TestEntryPointDiscovery.test_a_backend_is_added_by_an_entry_point_alone`,
which is Phase 1's first acceptance criterion made executable: it registers a
backend defined *inside this test file* through nothing but an entry point, and
asserts the registry finds and uses it. If that ever needs a change to
``tokenmill.core.registry`` to keep passing, the plugin architecture has stopped
being real.
"""

from __future__ import annotations

from importlib.metadata import EntryPoint
from pathlib import Path

import pytest

from tests.doubles import EchoConverter
from tokenmill.core.errors import BackendUnavailable, UnsupportedFormat
from tokenmill.core.models import (
    Availability,
    Domain,
    IsolationMode,
    LicenseTier,
    Source,
)
from tokenmill.core.registry import (
    BACKEND_ENTRY_POINT_GROUP,
    Registry,
    default_registry,
    reset_default_registry,
)


def ep(name: str, value: str) -> EntryPoint:
    """Build an entry point pointing at a dotted path.

    Args:
        name: The entry point name.
        value: ``module:attribute``.

    Returns:
        The entry point.
    """
    return EntryPoint(name=name, value=value, group=BACKEND_ENTRY_POINT_GROUP)


class DiscoverableConverter(EchoConverter):
    """A backend that exists only in this test module."""

    def __init__(self) -> None:
        super().__init__("discoverable", output="found me", input_formats=("txt", "quux"))


class NotAConverter:
    """An entry point target that does not implement the protocol."""


def broken_factory() -> None:
    """Raise on load, as a plugin with a bad dependency would.

    Raises:
        ImportError: Always.
    """
    msg = "No module named 'definitely_not_installed'"
    raise ImportError(msg)


class TestEntryPointDiscovery:
    def test_a_backend_is_added_by_an_entry_point_alone(self, tmp_path: Path) -> None:
        """Acceptance criterion 1: no core edit is needed to add a backend."""
        registry = Registry()
        registry.load_from([ep("discoverable", f"{__name__}:DiscoverableConverter")])

        assert "discoverable" in registry
        source = Source.from_path(_write(tmp_path, "a.quux", "content"))
        assert registry.select(source).info.id == "discoverable"

    def test_discovery_runs_once_and_is_cached(self) -> None:
        """Entry point scanning imports every plugin, so it must not repeat."""
        registry = Registry()
        converter = DiscoverableConverter()
        registry.register(converter)

        for _ in range(5):
            registry.get("discoverable").is_available()

        # One probe, not five: the availability cache is what keeps a `backends`
        # listing cheap.
        assert converter.calls == 1

    def test_the_real_entry_points_expose_both_reference_backends(self) -> None:
        registry = Registry()

        assert {"plaintext", "markdownify_html"} <= set(registry.ids())

    def test_default_registry_is_process_wide(self) -> None:
        reset_default_registry()
        try:
            assert default_registry() is default_registry()
        finally:
            reset_default_registry()


class TestBrokenPlugins:
    """A third-party plugin's bug must never take the process down."""

    def test_a_plugin_that_raises_on_import_is_recorded_not_raised(self) -> None:
        registry = Registry()

        registry.load_from([ep("brokenplugin", f"{__name__}:broken_factory")])

        assert [b.id for b in registry.broken] == ["brokenplugin"]
        assert "definitely_not_installed" in registry.broken[0].error

    def test_a_broken_plugin_does_not_hide_the_working_ones(self) -> None:
        registry = Registry()

        registry.load_from(
            [
                ep("brokenplugin", f"{__name__}:broken_factory"),
                ep("discoverable", f"{__name__}:DiscoverableConverter"),
            ]
        )

        assert "discoverable" in registry
        assert len(registry) == 1
        assert len(registry.broken) == 1

    def test_asking_for_a_broken_backend_reports_it_as_unavailable(self) -> None:
        registry = Registry()
        registry.load_from([ep("brokenplugin", f"{__name__}:broken_factory")])

        with pytest.raises(BackendUnavailable, match="failed to load"):
            registry.get("brokenplugin")

    def test_a_broken_backend_reports_broken_availability(self) -> None:
        registry = Registry()
        registry.load_from([ep("brokenplugin", f"{__name__}:broken_factory")])

        availability = registry.broken[0].availability

        assert not availability
        assert not availability.is_available

    def test_an_entry_point_that_is_not_a_converter_is_rejected(self) -> None:
        registry = Registry()

        registry.load_from([ep("bogus", f"{__name__}:NotAConverter")])

        assert len(registry) == 0
        assert "does not implement the Converter protocol" in registry.broken[0].error

    def test_a_missing_entry_point_target_is_recorded_not_raised(self) -> None:
        registry = Registry()

        registry.load_from([ep("gone", f"{__name__}:no_such_attribute")])

        assert [b.id for b in registry.broken] == ["gone"]


class TestAvailabilityDegradation:
    """Acceptance criterion 2: correct availability when a dependency is absent."""

    def test_a_backend_with_a_missing_dependency_is_listed_but_unavailable(self) -> None:
        registry = Registry()
        registry.register(
            EchoConverter("needy", availability=Availability.missing_dependency("nonexistent_pkg"))
        )

        converter = registry.get("needy")

        assert "needy" in registry
        assert not converter.is_available()
        assert converter.is_available().hint == "pip install nonexistent_pkg"

    def test_an_unavailable_backend_is_skipped_by_auto_selection(self, tmp_path: Path) -> None:
        registry = Registry()
        registry.register(
            EchoConverter(
                "needy",
                availability=Availability.missing_dependency("nope"),
                priority=100,
            )
        )
        registry.register(EchoConverter("works", priority=1))

        chosen = registry.select(Source.from_path(_write(tmp_path, "a.txt", "x")))

        # Higher priority, but it cannot run, so the working one wins.
        assert chosen.info.id == "works"

    def test_asking_for_an_unavailable_backend_by_name_is_an_error(self, tmp_path: Path) -> None:
        registry = Registry()
        registry.register(
            EchoConverter("needy", availability=Availability.missing_dependency("nope"))
        )

        with pytest.raises(BackendUnavailable, match="missing dependency"):
            registry.select(Source.from_path(_write(tmp_path, "a.txt", "x")), backend_id="needy")

    def test_a_probe_that_raises_degrades_to_broken(self) -> None:
        class ExplodingProbe(EchoConverter):
            def _probe(self) -> Availability:
                msg = "probe blew up"
                raise RuntimeError(msg)

        converter = ExplodingProbe("wobbly")

        availability = converter.is_available()

        assert not availability
        assert "probe blew up" in availability.describe()


class TestSelection:
    def test_priority_then_isolation_then_id_decide(self, tmp_path: Path) -> None:
        registry = Registry()
        registry.register(EchoConverter("low", priority=1))
        registry.register(EchoConverter("high", priority=9))

        source = Source.from_path(_write(tmp_path, "a.txt", "x"))

        assert registry.select(source).info.id == "high"

    def test_in_process_beats_out_of_process_at_equal_priority(self, tmp_path: Path) -> None:
        registry = Registry()
        registry.register(
            EchoConverter(
                "far",
                priority=5,
                isolation=IsolationMode.SUBPROCESS,
                license="GPL-3.0",
                license_tier=LicenseTier.COPYLEFT,
            )
        )
        registry.register(EchoConverter("near", priority=5))

        source = Source.from_path(_write(tmp_path, "a.txt", "x"))

        assert registry.select(source).info.id == "near"

    def test_selection_is_deterministic_regardless_of_registration_order(
        self, tmp_path: Path
    ) -> None:
        source_path = _write(tmp_path, "a.txt", "x")

        first = Registry()
        first.register(EchoConverter("alpha", priority=5))
        first.register(EchoConverter("beta", priority=5))
        second = Registry()
        second.register(EchoConverter("beta", priority=5))
        second.register(EchoConverter("alpha", priority=5))

        source = Source.from_path(source_path)

        assert first.select(source).info.id == second.select(source).info.id == "alpha"

    def test_an_explicit_backend_is_never_silently_substituted(self, tmp_path: Path) -> None:
        """Substituting would make every measurement unattributable."""
        registry = Registry()
        registry.register(EchoConverter("preferred", priority=100))
        registry.register(EchoConverter("asked_for", priority=1))

        chosen = registry.select(
            Source.from_path(_write(tmp_path, "a.txt", "x")), backend_id="asked_for"
        )

        assert chosen.info.id == "asked_for"

    def test_an_unknown_format_says_what_is_supported(self, tmp_path: Path) -> None:
        registry = Registry()
        registry.register(EchoConverter("txtonly", input_formats=("txt",)))

        with pytest.raises(UnsupportedFormat) as excinfo:
            registry.select(Source.from_path(_write(tmp_path, "a.wat", "x")))

        assert "txt" in str(excinfo.value)

    def test_a_format_handled_only_by_an_unavailable_backend_says_so(self, tmp_path: Path) -> None:
        """Not-installed and not-supported need different user actions."""
        registry = Registry()
        registry.register(
            EchoConverter(
                "needy",
                input_formats=("pdf",),
                availability=Availability.missing_dependency("nope"),
            )
        )

        with pytest.raises(UnsupportedFormat) as excinfo:
            registry.select(Source.from_path(_write(tmp_path, "a.pdf", "x")))

        assert "cannot run" in str(excinfo.value)
        assert "needy" in str(excinfo.value)

    def test_an_unknown_backend_id_lists_the_known_ones(self) -> None:
        registry = Registry()
        registry.register(EchoConverter("real"))

        with pytest.raises(BackendUnavailable, match="no backend named"):
            registry.get("imaginary")


class TestLicencePolicy:
    def test_registering_a_copyleft_in_process_backend_is_refused(self) -> None:
        """The registry re-checks, in case a plugin builds its info elsewhere."""
        registry = Registry()
        converter = EchoConverter("sneaky")
        object.__setattr__(converter.info, "license_tier", LicenseTier.COPYLEFT)

        with pytest.raises(ValueError, match="refusing to register"):
            registry.register(converter)


class TestLookup:
    def test_for_domain_filters_and_orders(self) -> None:
        registry = Registry()
        registry.register(EchoConverter("web_one", domains=(Domain.WEB,), priority=1))
        registry.register(EchoConverter("web_two", domains=(Domain.WEB,), priority=9))
        registry.register(EchoConverter("doc", domains=(Domain.DOCUMENTS,)))

        ids = [c.info.id for c in registry.for_domain(Domain.WEB)]

        assert ids == ["web_two", "web_one"]

    def test_known_formats_is_the_union_over_backends(self) -> None:
        registry = Registry()
        registry.register(EchoConverter("a", input_formats=("txt", "md")))
        registry.register(EchoConverter("b", input_formats=("md", "html")))

        assert registry.known_formats() == ("html", "md", "txt")

    def test_registering_the_same_id_twice_is_refused(self) -> None:
        registry = Registry()
        registry.register(EchoConverter("dup"))

        with pytest.raises(ValueError, match="already registered"):
            registry.register(EchoConverter("dup"))

    def test_a_duplicate_entry_point_id_keeps_the_first(self) -> None:
        registry = Registry()

        registry.load_from(
            [
                ep("first", f"{__name__}:DiscoverableConverter"),
                ep("second", f"{__name__}:DiscoverableConverter"),
            ]
        )

        assert len(registry) == 1

    def test_iteration_is_sorted_by_id(self) -> None:
        registry = Registry()
        registry.register(EchoConverter("zulu"))
        registry.register(EchoConverter("alpha"))

        assert [c.info.id for c in registry] == ["alpha", "zulu"]


def _write(directory: Path, name: str, content: str) -> Path:
    """Write a file and return its path.

    Args:
        directory: Where to write it.
        name: The file name.
        content: What to write.

    Returns:
        The path written.
    """
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path
