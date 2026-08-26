"""The table encoders, and the property that every one of them round-trips.

`hypothesis` has been a declared dev dependency since Phase 0 and unused until
now. This is what it was for: the acceptance criterion is that the encoders
round-trip tabular data losslessly, and losslessness is a claim about all
inputs rather than about the three a person thinks of.

The generated cells deliberately include the values that break naive encoders —
embedded delimiters, quotes, backslashes, leading zeros, exponent notation,
`true`, empty strings, leading and trailing spaces, and control characters —
because each one is a real way a converter's output can look.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tokenmill.formats import (
    Table,
    TableEncoderRegistry,
    TableError,
    default_format_registry,
)
from tokenmill.formats._scalars import as_cell, as_native, renders_natively

#: Formats that key each row by column name and therefore need distinct,
#: non-empty column names.
RECORD_FORMATS = ("json", "toon", "keyvalue")

#: Every registered format id.
ALL_FORMATS = ("csv", "json", "keyvalue", "markdown", "toon")

#: Values chosen to break encoders: delimiters, quote characters, escapes,
#: number-like strings that must not be reformatted, and the keywords a
#: decoder could mistake for a type.
AWKWARD = [
    "",
    " ",
    "  padded  ",
    "a,b",
    "a|b",
    'say "hi"',
    "back\\slash",
    "semi:colon",
    "05",
    "+1",
    "1e-6",
    "9.99",
    "-3",
    "true",
    "false",
    "null",
    "TRUE",
    "#hash",
    "-dash",
    "[bracket]",
    "{brace}",
    "tab\there",
    "line\nbreak",
    "emoji 🙂",
    "naïve",
]

cells = st.one_of(
    st.sampled_from(AWKWARD),
    st.text(max_size=12),
)

#: Column names for the record-shaped formats: non-empty and made distinct by
#: the strategy rather than by filtering, so shrinking stays useful.
names = (
    st.text(alphabet=st.characters(blacklist_categories=("Cs", "Cc")), min_size=1, max_size=8)
    .map(str.strip)
    .filter(bool)
)


@st.composite
def tables(draw: st.DrawFn, *, unique_headers: bool = True, allow_newlines: bool = True) -> Table:
    """Generate a table.

    Args:
        draw: Hypothesis' draw function.
        unique_headers: Whether column names must be distinct and non-empty.
        allow_newlines: Whether cells may contain line breaks. A Markdown pipe
            table cannot represent one, which is documented rather than fixed.

    Returns:
        The generated table.
    """
    width = draw(st.integers(min_value=1, max_value=4))
    if unique_headers:
        headers = draw(st.lists(names, min_size=width, max_size=width, unique=True))
    else:
        headers = draw(st.lists(st.text(max_size=6), min_size=width, max_size=width))

    if allow_newlines:
        cell = cells
    else:
        # The Markdown encoder's two documented, format-inherent losses: a pipe
        # table cannot carry a line break, and cell padding is not content.
        cell = cells.filter(lambda c: "\n" not in c and "\r" not in c and c == c.strip())
    # At least one row: the general round-trip property is about tables that
    # carry data. The zero-row case is format-inherent (JSON's array of
    # objects has nowhere to put column names) and is covered explicitly.
    rows = draw(st.lists(st.lists(cell, min_size=width, max_size=width), min_size=1, max_size=4))
    return Table.of(headers, rows)


@pytest.fixture(scope="module")
def registry() -> TableEncoderRegistry:
    return default_format_registry()


class TestEveryFormatRoundTrips:
    """The Phase 5 acceptance criterion, as a property rather than an example."""

    @pytest.mark.parametrize("format_id", ["csv", "json", "toon", "keyvalue"])
    @given(table=tables())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_encoding_then_decoding_returns_the_same_table(
        self, format_id: str, table: Table
    ) -> None:
        encoder = default_format_registry().get(format_id)
        assert encoder.decode(encoder.encode(table)) == table

    @given(table=tables(allow_newlines=False))
    @settings(max_examples=200)
    def test_markdown_round_trips_for_cells_without_line_breaks(self, table: Table) -> None:
        # A GFM pipe table is line-oriented and cannot carry a line break in a
        # cell. That limit is the format's, is documented on the encoder, and
        # is the reason this property is stated separately rather than the
        # whole suite being weakened to match it.
        encoder = default_format_registry().get("markdown")
        assert encoder.decode(encoder.encode(table)) == table

    @given(table=tables(allow_newlines=False))
    @settings(max_examples=100)
    def test_every_markdown_row_is_exactly_one_line(self, table: Table) -> None:
        # The invariant the two documented losses buy, and the reason a pipe
        # table can be read back by anything that splits on newlines.
        encoder = default_format_registry().get("markdown")
        body = encoder.encode(table).rstrip("\n").split("\n")
        assert len(body) == len(table.rows) + 2

    @pytest.mark.parametrize("format_id", ["csv", "markdown", "toon", "keyvalue"])
    def test_an_empty_table_keeps_its_columns(
        self, format_id: str, registry: TableEncoderRegistry
    ) -> None:
        table = Table.of(["a", "b"], [])
        encoder = registry.get(format_id)
        assert encoder.decode(encoder.encode(table)) == table

    def test_json_cannot_keep_the_columns_of_an_empty_table(
        self, registry: TableEncoderRegistry
    ) -> None:
        # Format-inherent: an array of objects carries its column names on the
        # objects. Documented on the encoder rather than fixed with a wrapper
        # object that would add tokens to every row of every comparison.
        encoder = registry.get("json")
        assert encoder.encode(Table.of(["a", "b"], [])) == "[]\n"
        assert encoder.decode("[]\n") == Table.of((), ())

    def test_a_row_of_empty_cells_is_not_mistaken_for_an_empty_table(
        self, registry: TableEncoderRegistry
    ) -> None:
        # Key-value writes no rows as bare `key:` and an empty cell as `key: ""`.
        # Deciding which on the decoded value confused the two.
        table = Table.of(["a"], [[""]])
        encoder = registry.get("keyvalue")
        assert encoder.decode(encoder.encode(table)) == table

    def test_a_cell_containing_an_exotic_line_separator_survives(
        self, registry: TableEncoderRegistry
    ) -> None:
        # str.splitlines() breaks on U+0085, U+2028, U+2029, \x0b and \x0c.
        # Every decoder here splits on LF only.
        for char in ("\x85", "\u2028", "\u2029", "\x0b", "\x0c"):
            table = Table.of(["a"], [[f"x{char}y"]])
            for format_id in ("csv", "json", "toon", "keyvalue"):
                encoder = registry.get(format_id)
                assert encoder.decode(encoder.encode(table)) == table, (format_id, char)


class TestColumnsThatCannotBeKeys:
    """MarkItDown really does emit a table with three unnamed columns."""

    @pytest.mark.parametrize("format_id", RECORD_FORMATS)
    def test_unnamed_columns_are_refused_rather_than_silently_dropped(
        self, format_id: str, registry: TableEncoderRegistry
    ) -> None:
        table = Table.of(["", "", ""], [["Stage", "Tokens", "Delta"]])
        with pytest.raises(TableError, match="no name"):
            registry.get(format_id).encode(table)

    @pytest.mark.parametrize("format_id", RECORD_FORMATS)
    def test_repeated_column_names_are_refused(
        self, format_id: str, registry: TableEncoderRegistry
    ) -> None:
        table = Table.of(["a", "a"], [["1", "2"]])
        with pytest.raises(TableError, match="repeated"):
            registry.get(format_id).encode(table)

    @pytest.mark.parametrize("format_id", ["markdown", "csv"])
    def test_positional_formats_accept_them(
        self, format_id: str, registry: TableEncoderRegistry
    ) -> None:
        table = Table.of(["", "", ""], [["Stage", "Tokens", "Delta"]])
        encoder = registry.get(format_id)
        assert encoder.decode(encoder.encode(table)) == table


class TestScalarsAreOnlyDemotedNeverPromoted:
    """The rule that keeps numeric cells realistic and still exact."""

    @pytest.mark.parametrize(
        ("cell", "native"),
        [
            ("9.99", True),
            ("42", True),
            ("0", True),
            ("true", True),
            ("null", True),
            ("05", False),
            ("+1", False),
            ("1e-6", False),
            ("TRUE", False),
            (" 1", False),
            ("", False),
            ("abc", False),
        ],
    )
    def test_a_cell_is_written_natively_only_when_it_renders_back_identically(
        self, cell: str, native: bool
    ) -> None:
        assert renders_natively(cell) is native

    @given(cell=cells)
    @settings(max_examples=300)
    def test_the_native_round_trip_is_exact_for_every_cell(self, cell: str) -> None:
        assert as_cell(as_native(cell)) == cell

    def test_the_comparison_is_not_rigged_in_csv_s_favour(
        self, registry: TableEncoderRegistry
    ) -> None:
        # If cells were always strings, JSON and TOON would quote numbers that
        # CSV writes bare, and CSV would win the comparison on a technicality.
        table = Table.of(["id", "price"], [["1", "9.99"], ["2", "14.50"]])
        assert '"1"' not in registry.get("json").encode(table)
        assert '"1"' not in registry.get("toon").encode(table)

    def test_a_leading_zero_is_still_quoted(self, registry: TableEncoderRegistry) -> None:
        table = Table.of(["code"], [["05"]])
        assert '"05"' in registry.get("json").encode(table)
        assert '"05"' in registry.get("toon").encode(table)


class TestToonAgainstTheSpecification:
    """Working Draft 4.1, `github.com/toon-format/spec`, fetched 2026-08-24."""

    def test_the_tabular_header_declares_length_and_fields_once(
        self, registry: TableEncoderRegistry
    ) -> None:
        table = Table.of(["id", "name", "role"], [["1", "Ada", "admin"], ["2", "Bob", "user"]])
        encoded = registry.get("toon").encode(table)
        assert encoded.splitlines()[0] == "rows[2]{id,name,role}:"
        assert encoded.splitlines()[1] == "  1,Ada,admin"

    def test_the_default_comma_delimiter_is_omitted_from_the_bracket_segment(
        self, registry: TableEncoderRegistry
    ) -> None:
        # Spec section 6 makes the delimiter optional and comma the default.
        # `toon-py` 1.0.2 emits `[2,]` here; the spec's own example is `[2]`.
        table = Table.of(["a"], [["x"], ["y"]])
        assert registry.get("toon").encode(table).startswith("rows[2]{a}:")

    def test_rows_are_indented_by_two_spaces(self, registry: TableEncoderRegistry) -> None:
        table = Table.of(["a"], [["x"]])
        assert registry.get("toon").encode(table).splitlines()[1] == "  x"

    def test_a_declared_length_that_disagrees_with_the_rows_is_refused(
        self, registry: TableEncoderRegistry
    ) -> None:
        with pytest.raises(TableError, match="declares 5 rows"):
            registry.get("toon").decode("rows[5]{a}:\n  x\n")

    def test_a_row_of_the_wrong_width_is_refused(self, registry: TableEncoderRegistry) -> None:
        with pytest.raises(TableError, match="cells"):
            registry.get("toon").decode("rows[1]{a,b}:\n  x\n")

    def test_the_list_form_is_refused_rather_than_half_read(
        self, registry: TableEncoderRegistry
    ) -> None:
        with pytest.raises(TableError, match="tabular form only"):
            registry.get("toon").decode("items[2]:\n  - 1\n  - 2\n")

    def test_an_unterminated_quoted_cell_is_refused(self, registry: TableEncoderRegistry) -> None:
        with pytest.raises(TableError, match="unterminated"):
            registry.get("toon").decode('rows[1]{a}:\n  "x\n')

    def test_an_undefined_escape_is_refused(self, registry: TableEncoderRegistry) -> None:
        with pytest.raises(TableError, match="undefined escape"):
            registry.get("toon").decode('rows[1]{a}:\n  "a\\qb"\n')

    def test_a_control_character_is_escaped(self, registry: TableEncoderRegistry) -> None:
        table = Table.of(["a"], [["x\x01y"]])
        encoded = registry.get("toon").encode(table)
        assert "\\u0001" in encoded
        assert registry.get("toon").decode(encoded) == table


class TestTheRegistry:
    def test_every_built_in_format_is_discovered_through_entry_points(
        self, registry: TableEncoderRegistry
    ) -> None:
        assert set(registry.ids()) >= set(ALL_FORMATS)

    def test_an_unknown_format_lists_the_known_ones(self, registry: TableEncoderRegistry) -> None:
        with pytest.raises(KeyError, match="toon"):
            registry.get("nope")

    def test_every_encoder_declares_its_metadata(self, registry: TableEncoderRegistry) -> None:
        for encoder in registry:
            assert encoder.id
            assert encoder.name
            assert encoder.description
            assert "/" in encoder.media_type


class TestReadingRealConverterOutput:
    """The Markdown decoder has to read what thirteen backends emit."""

    def test_a_table_without_outer_pipes_is_read(self, registry: TableEncoderRegistry) -> None:
        text = "a | b\n--- | ---\n1 | 2\n"
        assert registry.get("markdown").decode(text) == Table.of(["a", "b"], [["1", "2"]])

    def test_alignment_colons_are_ignored(self, registry: TableEncoderRegistry) -> None:
        text = "| a | b |\n| :--- | ---: |\n| 1 | 2 |\n"
        assert registry.get("markdown").decode(text) == Table.of(["a", "b"], [["1", "2"]])

    def test_prose_around_the_table_is_skipped(self, registry: TableEncoderRegistry) -> None:
        text = "Intro paragraph.\n\n| a |\n| --- |\n| 1 |\n"
        assert registry.get("markdown").decode(text) == Table.of(["a"], [["1"]])

    def test_text_with_no_table_is_refused(self, registry: TableEncoderRegistry) -> None:
        with pytest.raises(TableError, match="no Markdown table"):
            registry.get("markdown").decode("just prose\n")

    def test_pipes_without_a_delimiter_row_are_not_a_table(
        self, registry: TableEncoderRegistry
    ) -> None:
        with pytest.raises(TableError):
            registry.get("markdown").decode("| a | b |\n| 1 | 2 |\n")


class TestTheOnePipeTableParser:
    r"""Defect N3: two pipe-table parsers existed, and now there is one.

    `tokenmill.fidelity.markdown` had its own scanner, written separately and
    deliberately less forgiving. Two implementations of one syntax is a bug
    reported twice and fixed once, so the difference became an argument to
    `scan_tables` instead of a second copy of the algorithm.

    These assert that the flag is load-bearing — that `unescape` genuinely
    changes the answer — because a strictness flag nobody can see the effect of
    is indistinguishable from a merge that quietly dropped one behaviour.
    """

    def test_fidelity_no_longer_carries_a_parser_of_its_own(self) -> None:
        """Guard the guard: if a second parser reappears there, fail here.

        Named after what actually went wrong. `fidelity.markdown` used to define
        `_split_row` and its own copy of the delimiter pattern; both are gone,
        and their return would be the third implementation this merge exists to
        prevent.
        """
        from tokenmill.fidelity import markdown as fid

        assert not hasattr(fid, "_split_row")
        assert not hasattr(fid, "_DELIMITER_RE")

    def test_fidelity_and_the_encoder_agree_on_where_a_table_is(self) -> None:
        """The same block, read by both callers, is the same table."""
        from tokenmill.fidelity.markdown import tables
        from tokenmill.formats.markdown_table import scan_tables

        text = "| a | b |\n| --- | --- |\n| 1 | 2 |\n"

        (measured,) = tables(text)
        (scanned,) = scan_tables([ln for ln in text.split("\n") if ln.strip()])

        assert measured.rows == scanned

    def test_unescape_true_rejoins_a_cell_containing_an_escaped_pipe(self) -> None:
        r"""Round-tripping must undo `\|`, or the row tears in half."""
        from tokenmill.formats.markdown_table import scan_tables

        lines = [r"| a | b |", "| --- | --- |", r"| x \| y | z |"]

        (table,) = scan_tables(lines, unescape=True)

        assert table[1] == ("x | y", "z"), "the escaped pipe is one cell, not two"

    def test_unescape_false_keeps_the_backslash_it_did_not_write(self) -> None:
        r"""Fidelity scores converter output, which we never escaped.

        Treating `\` as an escape character there would silently alter the
        content being measured, so the same input splits differently — and
        that difference is the whole reason the flag exists.
        """
        from tokenmill.formats.markdown_table import scan_tables

        lines = [r"| a | b |", "| --- | --- |", r"| x \| y | z |"]

        (table,) = scan_tables(lines, unescape=False)

        assert table[1] == ("x \\", "y", "z"), (
            "without unescaping, the backslash is content and the pipe is a "
            "column boundary, so the same row is three cells rather than two"
        )
        assert len(scan_tables(lines, unescape=True)[0][1]) == 2, (
            "and the flag is what makes the difference, on identical input"
        )

    def test_a_delimiter_row_is_what_makes_pipes_a_table(self) -> None:
        from tokenmill.formats.markdown_table import is_delimiter_row, scan_tables

        assert is_delimiter_row("| --- | :---: |")
        assert not is_delimiter_row("| a | b |")
        assert scan_tables(["| a | b |", "| 1 | 2 |"]) == []

    def test_limit_stops_early_and_none_finds_them_all(self) -> None:
        from tokenmill.formats.markdown_table import scan_tables

        lines = [
            "| a |",
            "| --- |",
            "| 1 |",
            "",
            "| b |",
            "| --- |",
            "| 2 |",
        ]

        assert len(scan_tables(lines, limit=1)) == 1
        assert len(scan_tables(lines)) == 2

    def test_the_delimiter_row_is_punctuation_and_is_not_returned(self) -> None:
        from tokenmill.formats.markdown_table import scan_tables

        (table,) = scan_tables(["| a | b |", "| --- | --- |", "| 1 | 2 |"])

        assert table == (("a", "b"), ("1", "2"))
