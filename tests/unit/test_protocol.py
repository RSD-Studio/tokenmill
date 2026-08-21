"""The protocol-conformance suite that every backend must pass.

This is Phase 1's exit gate. It is parametrised over **every backend the
installed entry points expose**, not over a hard-coded list, so a backend added
in Phase 2 or by a third party is held to the same contract the moment it is
installed — without anyone remembering to add it here.

What it checks is the set of promises the registry, the pipeline and the CLI all
rely on: metadata is well-formed, the licence policy holds, availability probes
are cheap, honest and never raise, format support is consistent, and a
conversion either returns text or raises something inside the taxonomy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.doubles import EchoConverter, ExplodingConverter
from tokenmill.core.errors import ConversionError
from tokenmill.core.models import (
    ConvertOptions,
    Domain,
    IsolationMode,
    LicenseTier,
    OutputFormat,
    Source,
)
from tokenmill.core.protocol import Converter
from tokenmill.core.registry import Registry

#: Formats that name a kind of source rather than a file extension, so there is
#: no file whose name could carry them.
_PSEUDO_FORMATS = frozenset({"text", "url", "repo"})


def _installed_backends() -> list[Converter]:
    """Return every backend the installed entry points expose.

    Returns:
        The backends, ordered by id.
    """
    return list(Registry())


def _backend_id(converter: Converter) -> str:
    """Return a readable parametrisation id.

    Args:
        converter: The backend.

    Returns:
        Its id.
    """
    return converter.info.id


BACKENDS = _installed_backends()


def test_both_reference_backends_are_installed() -> None:
    """Guard the suite below: parametrising over an empty list passes vacuously."""
    ids = {c.info.id for c in BACKENDS}

    assert {"plaintext", "markdownify_html"} <= ids, (
        "the reference backends are missing; run `uv sync` so the entry points "
        "are registered, otherwise the conformance suite tests nothing"
    )


@pytest.mark.parametrize("converter", BACKENDS, ids=_backend_id)
class TestProtocolConformance:
    def test_it_implements_the_protocol(self, converter: Converter) -> None:
        assert isinstance(converter, Converter)

    def test_its_id_is_a_stable_lowercase_token(self, converter: Converter) -> None:
        backend_id = converter.info.id

        assert backend_id
        assert backend_id == backend_id.lower()
        assert " " not in backend_id

    def test_its_metadata_is_complete(self, converter: Converter) -> None:
        info = converter.info

        assert info.name
        assert info.description
        assert info.upstream_url.startswith("http")
        assert info.domains
        assert all(isinstance(domain, Domain) for domain in info.domains)

    def test_it_declares_a_licence_and_a_tier(self, converter: Converter) -> None:
        """Licence is enforced metadata, not documentation."""
        info = converter.info

        assert info.license
        assert isinstance(info.license_tier, LicenseTier)

    def test_a_non_permissive_backend_runs_out_of_process(self, converter: Converter) -> None:
        """CONTRIBUTING.md rule 2: AGPL/GPL code is never imported."""
        info = converter.info

        if info.license_tier is not LicenseTier.PERMISSIVE:
            assert info.isolation is not IsolationMode.IN_PROCESS

    def test_its_input_formats_are_bare_lowercase_tokens(self, converter: Converter) -> None:
        formats = converter.info.input_formats

        assert formats
        assert len(set(formats)) == len(formats), "duplicate input formats"
        for fmt in formats:
            assert fmt == fmt.lower()
            assert not fmt.startswith("."), "declare 'pdf', not '.pdf'"

    def test_it_declares_at_least_one_output_format(self, converter: Converter) -> None:
        outputs = converter.info.output_formats

        assert outputs
        assert all(isinstance(fmt, OutputFormat) for fmt in outputs)

    def test_availability_never_raises(self, converter: Converter) -> None:
        availability = converter.is_available()

        assert availability.describe()

    def test_availability_is_cached(self, converter: Converter) -> None:
        """Probes run for every listing, so they must be answered from cache."""
        assert converter.is_available() is converter.is_available()

    def test_an_unavailable_backend_offers_a_way_forward(self, converter: Converter) -> None:
        availability = converter.is_available()

        if not availability:
            assert availability.hint, "an unavailable backend must say how to fix it"

    def test_supports_agrees_with_the_declared_formats(
        self, converter: Converter, tmp_path: Path
    ) -> None:
        for fmt in converter.info.input_formats:
            if fmt in _PSEUDO_FORMATS:
                continue
            assert converter.supports(Source.from_path(_write(tmp_path, f"probe.{fmt}")))

    def test_it_rejects_a_format_it_does_not_claim(
        self, converter: Converter, tmp_path: Path
    ) -> None:
        source = Source.from_path(_write(tmp_path, "probe.definitelynotaformat"))

        assert not converter.supports(source)

    def test_converting_an_unsupported_source_raises_inside_the_taxonomy(
        self, converter: Converter, tmp_path: Path
    ) -> None:
        source = Source.from_path(_write(tmp_path, "probe.definitelynotaformat"))

        if not converter.is_available():
            pytest.skip(f"{converter.info.id} is not available here")

        with pytest.raises(ConversionError):
            converter.convert(source, ConvertOptions())

    def test_it_converts_a_source_it_claims(self, converter: Converter, tmp_path: Path) -> None:
        if not converter.is_available():
            pytest.skip(f"{converter.info.id} is not available here")

        source = _plausible_source(converter, tmp_path)
        if source is None:
            pytest.skip(f"no plausible sample for {converter.info.id}")

        result = converter.convert(source, ConvertOptions())

        assert isinstance(result.text, str)
        assert result.backend_id == converter.info.id
        assert result.duration_s >= 0
        assert result.output_format in converter.info.output_formats

    def test_a_result_carries_no_token_counts(self, converter: Converter, tmp_path: Path) -> None:
        """Backends convert; the pipeline measures.

        A backend that counted tokens itself would have to know about
        tokenizers, and its numbers would bypass the per-stage accounting.
        """
        if not converter.is_available():
            pytest.skip(f"{converter.info.id} is not available here")

        source = _plausible_source(converter, tmp_path)
        if source is None:
            pytest.skip(f"no plausible sample for {converter.info.id}")

        result = converter.convert(source, ConvertOptions())

        assert result.tokens_before is None
        assert result.tokens_after is None

    def test_it_refuses_a_source_over_the_size_limit(
        self, converter: Converter, tmp_path: Path
    ) -> None:
        if not converter.is_available():
            pytest.skip(f"{converter.info.id} is not available here")

        source = _plausible_source(converter, tmp_path)
        if source is None:
            pytest.skip(f"no plausible sample for {converter.info.id}")

        with pytest.raises(ConversionError, match="over the"):
            converter.convert(source, ConvertOptions(max_bytes=1))


def _write(directory: Path, name: str, content: str = "x") -> Path:
    """Write a small file and return its path.

    Args:
        directory: Where to write it.
        name: The file name, whose extension carries the format.
        content: What to write.

    Returns:
        The path written.
    """
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


def _plausible_source(converter: Converter, tmp_path: Path) -> Source | None:
    """Build a small, valid input for whatever this backend claims to convert.

    Args:
        converter: The backend to build a sample for.
        tmp_path: A directory to write the sample into.

    A backend claiming only formats with no sample here is skipped rather than
    failed. Adding a sample below is how a new format joins the suite.

    Returns:
        The source, or ``None`` if no sample is known for the backend's formats.
    """
    samples = {
        "txt": "Hello.\n",
        "md": "# Title\n\nBody.\n",
        "markdown": "# Title\n\nBody.\n",
        "rst": "Title\n=====\n",
        "log": "started\n",
        "html": "<html><body><h1>Title</h1><p>Body.</p></body></html>",
        "htm": "<html><body><h1>Title</h1><p>Body.</p></body></html>",
        "xhtml": "<html><body><h1>Title</h1><p>Body.</p></body></html>",
        "csv": "name,value\nalpha,1\n",
        "tsv": "name\tvalue\nalpha\t1\n",
        "json": '{"name": "alpha", "value": 1}',
        "xml": "<doc><name>alpha</name></doc>",
    }
    for fmt in converter.info.input_formats:
        content = samples.get(fmt)
        if content is None:
            continue
        path = tmp_path / f"sample.{fmt}"
        path.write_text(content, encoding="utf-8")
        return Source.from_path(path)
    return None


class TestBaseConverterContract:
    """The guarantees BaseConverter makes on every subclass's behalf."""

    def test_an_untyped_exception_is_wrapped_in_backendfailed(self, tmp_path: Path) -> None:
        """A backend's bug must still reach the user as a printable error."""
        converter = ExplodingConverter()

        with pytest.raises(ConversionError) as excinfo:
            converter.convert(Source.from_path(_write(tmp_path, "a.txt")), ConvertOptions())

        assert "this backend has a bug" in str(excinfo.value)
        assert excinfo.value.backend_id == "exploding"

    def test_warnings_and_metadata_reach_the_result(self, tmp_path: Path) -> None:
        converter = EchoConverter("noisy", warn="something looked odd")

        result = converter.convert(Source.from_path(_write(tmp_path, "a.txt")), ConvertOptions())

        assert result.warnings == ("something looked odd",)
        assert result.metadata["double"] is True

    def test_the_result_falls_back_to_a_format_the_backend_can_emit(self, tmp_path: Path) -> None:
        converter = EchoConverter("mdonly", output_formats=(OutputFormat.MARKDOWN,))

        result = converter.convert(
            Source.from_path(_write(tmp_path, "a.txt")),
            ConvertOptions(output_format=OutputFormat.TEXT),
        )

        assert result.output_format is OutputFormat.MARKDOWN
