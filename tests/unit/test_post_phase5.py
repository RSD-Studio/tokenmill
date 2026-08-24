"""Phase 5's post-processors, and the invariant that governs all of them.

The one test in here that matters most is
:meth:`TestTheDestructiveContract.test_the_default_chain_contains_nothing_destructive`.
It is asserted over the **whole registry** rather than per processor, because
the risk Phase 5 introduces is not that one of these is wrong — it is that the
sixth one somebody adds forgets the flag and quietly joins the default chain.
Phase 1 shipped one destructive post-processor; this phase ships five.

Everything else is checked against `tests/fixtures/structured.md`, which exists
so that composition is testable: stripping images must not disturb reference
definitions, heading normalisation must not touch the `#` inside a code fence,
and duplicate-block removal must not eat half a table.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tokenmill.core.models import ConvertOptions, ImageHandling, LinkHandling
from tokenmill.post.aggressive_whitespace import AggressiveWhitespaceCleaner
from tokenmill.post.base import default_post_registry
from tokenmill.post.dedupe import DuplicateBlockRemover
from tokenmill.post.frontmatter import FrontMatterStripper
from tokenmill.post.headings import HeadingNormalizer
from tokenmill.post.links import LinkHandler

#: The `bytes` tokenizer, because the chain now contains `chunk`, which asks
#: Chonkie to resolve the run's tokenizer. Under the default `o200k_base`
#: that is a vocabulary download, and this sandbox cannot reach one.
DEFAULTS = ConvertOptions(tokenizer="bytes")

#: Post-processors that need an optional dependency or a model download, and
#: so cannot be run in a whole-registry loop on a plain dev install. Their own
#: files cover them: `test_chunk.py` and `test_compress.py`.
NEEDS_A_DOWNLOAD = frozenset({"compress"})

#: Every post-processor Phase 5 added or changed.
PHASE_5_IDS = (
    "strip_frontmatter",
    "aggressive_whitespace",
    "dedupe_blocks",
    "normalize_headings",
)


@pytest.fixture(scope="module")
def structured(fixture_dir: Path) -> str:
    """Return the structured Markdown fixture."""
    return (fixture_dir / "structured.md").read_text(encoding="utf-8")


class TestTheDestructiveContract:
    """The invariant that keeps the default pipeline safe by construction."""

    def test_the_default_chain_contains_nothing_destructive(self) -> None:
        # Asserted over the registry, not per processor: the failure mode is a
        # new post-processor forgetting the flag, and a per-processor test
        # cannot catch one that was never written.
        for processor in default_post_registry().default_chain():
            assert processor.destructive is False, (
                f"{processor.id} is in the default chain and declares itself "
                f"destructive; default_chain() excludes destructive processors, "
                f"so this means the flag changed without the chain being rechecked"
            )

    def test_the_default_chain_is_still_only_whitespace_normalisation(self) -> None:
        # Phase 5 added five post-processors and none of them may have widened
        # what `tokenmill convert` does by default.
        assert [p.id for p in default_post_registry().default_chain()] == ["normalize_whitespace"]

    @pytest.mark.parametrize("processor_id", PHASE_5_IDS)
    def test_every_phase_5_post_processor_declares_itself_destructive(
        self, processor_id: str
    ) -> None:
        assert default_post_registry().get(processor_id).destructive is True

    @pytest.mark.parametrize("processor_id", PHASE_5_IDS)
    def test_a_user_who_asks_for_one_gets_it(self, processor_id: str) -> None:
        # Phase 1 learned that a flag which silently does nothing is worse than
        # no flag. Asking for a destructive processor by name must run it.
        chain = default_post_registry().resolve((processor_id,))
        assert [p.id for p in chain] == [processor_id]

    def test_every_registered_processor_declares_its_metadata(self) -> None:
        for processor in default_post_registry():
            assert processor.id
            assert processor.name
            assert processor.description
            assert isinstance(processor.destructive, bool)

    def test_orders_are_unique_so_the_chain_is_deterministic(self) -> None:
        orders = [p.order for p in default_post_registry()]
        assert len(orders) == len(set(orders))

    def test_every_processor_is_idempotent_on_the_structured_fixture(self, structured: str) -> None:
        # The protocol asks for idempotence where it is meaningful. Running a
        # chain twice must not keep changing the document.
        options = DEFAULTS.with_(image_handling=ImageHandling.ALT, link_handling=LinkHandling.STRIP)
        for processor in default_post_registry():
            if processor.id in NEEDS_A_DOWNLOAD:
                continue
            once = processor.process(structured, options)
            assert processor.process(once, options) == once, processor.id


class TestFrontMatterStripper:
    def test_it_removes_a_yaml_block(self, structured: str) -> None:
        out = FrontMatterStripper().process(structured, DEFAULTS)
        assert out.startswith("## A Structured Document")
        assert "draft: false" not in out

    def test_it_removes_a_toml_block(self) -> None:
        text = '+++\ntitle = "x"\n+++\n\n# Body\n'
        assert FrontMatterStripper().process(text, DEFAULTS) == "# Body\n"

    def test_a_thematic_break_mid_document_is_not_front_matter(self) -> None:
        text = "# Title\n\nSome prose.\n\n---\n\nMore prose.\n"
        assert FrontMatterStripper().process(text, DEFAULTS) == text

    def test_an_unterminated_block_is_left_alone(self) -> None:
        # The alternative is deleting the whole document because its first line
        # was a thematic break.
        text = "---\ntitle: x\n\nbody that never closes the block\n"
        assert FrontMatterStripper().process(text, DEFAULTS) == text

    def test_a_document_without_front_matter_is_untouched(self) -> None:
        text = "# Title\n\nBody.\n"
        assert FrontMatterStripper().process(text, DEFAULTS) == text

    def test_the_delimiters_must_match(self) -> None:
        text = "---\ntitle: x\n+++\n\nbody\n"
        assert FrontMatterStripper().process(text, DEFAULTS) == text


class TestHeadingNormalizer:
    def test_the_shallowest_heading_becomes_level_one(self, structured: str) -> None:
        out = HeadingNormalizer().process(structured, DEFAULTS)
        assert "# A Structured Document" in out
        assert "## A Structured Document" not in out

    def test_skipped_levels_are_closed_up(self, structured: str) -> None:
        # The fixture goes ## then #### then ###. A global remap of the distinct
        # levels emits #, ###, ## — still a skip. Walking the ancestor chain
        # emits #, ##, ##.
        out = HeadingNormalizer().process(structured, DEFAULTS)
        headings = [line for line in out.split("\n") if line.startswith("#")]
        assert headings[0] == "# A Structured Document"
        assert "## A heading that skips a level" in headings
        assert "## Measurements" in headings

    def test_a_hash_inside_a_code_fence_is_not_a_heading(self, structured: str) -> None:
        out = HeadingNormalizer().process(structured, DEFAULTS)
        assert "# This is a comment, not a heading." in out

    def test_front_matter_is_passed_through_untouched(self, structured: str) -> None:
        # A YAML block's closing `---` is indistinguishable from a setext
        # underline, so without this `draft: false` became a heading. Found by
        # reading the output, not by a test.
        out = HeadingNormalizer().process(structured, DEFAULTS)
        assert out.startswith("---\ntitle: A Structured Document")
        assert "# draft: false" not in out

    def test_setext_headings_become_atx(self) -> None:
        text = "Title\n=====\n\nSection\n-------\n\nBody.\n"
        out = HeadingNormalizer().process(text, DEFAULTS)
        assert "# Title" in out
        assert "## Section" in out
        assert "=====" not in out

    def test_a_document_with_no_headings_is_returned_unchanged(self) -> None:
        text = "Just prose.\n\nMore prose.\n"
        assert HeadingNormalizer().process(text, DEFAULTS) == text

    def test_a_list_item_above_a_rule_is_not_a_heading(self) -> None:
        text = "# Title\n\n- an item\n---\n"
        out = HeadingNormalizer().process(text, DEFAULTS)
        assert "- an item" in out
        assert "## an item" not in out


class TestDuplicateBlockRemover:
    def test_a_repeated_paragraph_is_removed_once(self, structured: str) -> None:
        out = DuplicateBlockRemover().process(structured, DEFAULTS)
        assert out.count("Structure carries meaning") == 1

    def test_the_first_occurrence_is_the_one_kept(self) -> None:
        block = "A" * 100
        text = f"{block}\n\nmiddle paragraph that is also quite long indeed yes\n\n{block}\n"
        out = DuplicateBlockRemover().process(text, DEFAULTS)
        assert out.index(block) < out.index("middle paragraph")

    def test_fenced_code_is_never_removed(self) -> None:
        fence = "```py\n" + "x = 1\n" * 20 + "```"
        text = f"{fence}\n\n{fence}\n"
        out = DuplicateBlockRemover().process(text, DEFAULTS)
        assert out.count("```py") == 2

    def test_short_blocks_are_left_alone(self) -> None:
        # Two sections called `### Notes` must both survive.
        text = "### Notes\n\nfirst\n\n### Notes\n\nsecond\n"
        out = DuplicateBlockRemover().process(text, DEFAULTS)
        assert out.count("### Notes") == 2

    def test_the_floor_is_configurable(self) -> None:
        text = "### Notes\n\nfirst\n\n### Notes\n\nsecond\n"
        options = DEFAULTS.with_(extra={"dedupe_min_chars": 3})
        out = DuplicateBlockRemover().process(text, options)
        assert out.count("### Notes") == 1

    def test_a_table_survives_intact(self, structured: str) -> None:
        out = DuplicateBlockRemover().process(structured, DEFAULTS)
        assert "| source | 16180 | - |" in out
        assert "| post-processed | 2980 | -81.6% |" in out

    def test_blocks_differing_only_in_whitespace_count_as_duplicates(self) -> None:
        # Comfortably over the 80-character floor, so the floor is not what is
        # being tested here.
        block = (
            "the quick brown fox jumps over the lazy dog and then keeps on "
            "running onwards well past the horizon"
        )
        text = f"{block}\n\n{block.replace(' ', '  ')}\n"
        assert DuplicateBlockRemover().process(text, DEFAULTS).count("quick") == 1


class TestAggressiveWhitespaceCleaner:
    def test_hard_line_breaks_are_removed(self, structured: str) -> None:
        # The thing normalize_whitespace deliberately preserves.
        out = AggressiveWhitespaceCleaner().process(structured, DEFAULTS)
        assert "  \n" not in out

    def test_runs_of_spaces_collapse(self) -> None:
        out = AggressiveWhitespaceCleaner().process("a     b\n", DEFAULTS)
        assert out == "a b\n"

    def test_fenced_code_is_untouched(self, structured: str) -> None:
        out = AggressiveWhitespaceCleaner().process(structured, DEFAULTS)
        assert '    return f"| {cell} |"' in out

    def test_list_indentation_survives(self, structured: str) -> None:
        out = AggressiveWhitespaceCleaner().process(structured, DEFAULTS)
        assert "   1. Nested detail under the last item" in out

    def test_an_indented_code_block_is_untouched(self) -> None:
        text = "para\n\n    x   =   1\n"
        assert "    x   =   1" in AggressiveWhitespaceCleaner().process(text, DEFAULTS)

    def test_an_inline_code_span_keeps_its_spacing(self) -> None:
        text = "see `a    b` here\n"
        assert "`a    b`" in AggressiveWhitespaceCleaner().process(text, DEFAULTS)

    def test_the_empty_string_stays_empty(self) -> None:
        assert AggressiveWhitespaceCleaner().process("   \n\n", DEFAULTS) == ""


class TestReferenceLinks:
    def test_inline_links_move_to_definitions(self, structured: str) -> None:
        out = LinkHandler().process(
            structured, DEFAULTS.with_(link_handling=LinkHandling.REFERENCE)
        )
        assert "[inline link][1]" in out
        assert "[1]: https://example.com/inline" in out

    def test_an_existing_definition_is_not_rewritten(self, structured: str) -> None:
        out = LinkHandler().process(
            structured, DEFAULTS.with_(link_handling=LinkHandling.REFERENCE)
        )
        assert "[ref-one]: https://example.com/reference" in out

    def test_a_repeated_target_is_defined_once(self) -> None:
        # The only case where reference mode actually saves anything.
        text = "[a](https://example.com/x) and [b](https://example.com/x)\n"
        out = LinkHandler().process(text, DEFAULTS.with_(link_handling=LinkHandling.REFERENCE))
        assert out.count("https://example.com/x") == 1
        assert "[a][1]" in out
        assert "[b][1]" in out

    def test_a_url_inside_a_code_fence_is_left_alone(self) -> None:
        text = "```\n[x](https://example.com/y)\n```\n"
        out = LinkHandler().process(text, DEFAULTS.with_(link_handling=LinkHandling.REFERENCE))
        assert out == text

    def test_keep_still_does_nothing(self, structured: str) -> None:
        assert LinkHandler().process(structured, DEFAULTS) == structured


class TestTheProcessorsCompose:
    """The reason the fixture has all of it at once."""

    def test_the_whole_destructive_chain_runs_without_damaging_the_table(
        self, structured: str
    ) -> None:
        options = DEFAULTS.with_(
            image_handling=ImageHandling.ALT, link_handling=LinkHandling.REFERENCE
        )
        text = structured
        for processor in default_post_registry():
            if processor.id in NEEDS_A_DOWNLOAD:
                continue
            text = processor.process(text, options)
        assert "| source | 16180 | - |" in text
        assert '    return f"| {cell} |"' in text
        assert text.count("Structure carries meaning") == 1
        assert not text.startswith("---\ntitle:")

    def test_the_chain_reduces_the_document(self, structured: str) -> None:
        options = DEFAULTS.with_(
            image_handling=ImageHandling.STRIP, link_handling=LinkHandling.STRIP
        )
        text = structured
        for processor in default_post_registry():
            if processor.id in NEEDS_A_DOWNLOAD:
                continue
            text = processor.process(text, options)
        assert len(text) < len(structured)
