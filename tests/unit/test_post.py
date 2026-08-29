"""Post-processors: the whitespace normaliser, link handling, and chain ordering."""

from __future__ import annotations

from importlib.metadata import EntryPoint

import pytest

from tokenmill.core.models import ConvertOptions, ImageHandling, LinkHandling, Source
from tokenmill.core.pipeline import Pipeline
from tokenmill.post.base import (
    POSTPROCESSOR_ENTRY_POINT_GROUP,
    BasePostProcessor,
    PostProcessContext,
    PostProcessor,
    PostProcessorRegistry,
    default_post_registry,
    reset_default_post_registry,
)
from tokenmill.post.links import LinkHandler
from tokenmill.post.whitespace import WhitespaceNormalizer

DEFAULTS = ConvertOptions()


def normalise(text: str) -> str:
    """Run the whitespace normaliser over ``text``.

    Args:
        text: The text to normalise.

    Returns:
        The normalised text.
    """
    return WhitespaceNormalizer().process(text, DEFAULTS)


class TestWhitespaceNormalizer:
    def test_it_is_not_destructive_and_runs_by_default(self) -> None:
        processor = WhitespaceNormalizer()

        assert processor.destructive is False
        assert processor.id in [p.id for p in default_post_registry().default_chain()]

    def test_line_endings_are_normalised(self) -> None:
        assert normalise("a\r\nb\rc") == "a\nb\nc\n"

    def test_a_stray_single_trailing_space_is_removed(self) -> None:
        assert normalise("heading \nbody\n") == "heading\nbody\n"

    def test_runs_of_blank_lines_collapse_to_one(self) -> None:
        assert normalise("a\n\n\n\n\nb") == "a\n\nb\n"

    def test_a_single_blank_line_survives_because_markdown_needs_it(self) -> None:
        assert normalise("# Title\n\nBody\n") == "# Title\n\nBody\n"

    def test_leading_and_trailing_blank_lines_go(self) -> None:
        assert normalise("\n\n\nbody\n\n\n") == "body\n"

    def test_the_output_ends_in_exactly_one_newline(self) -> None:
        assert normalise("body") == "body\n"

    def test_empty_input_stays_empty_rather_than_becoming_a_newline(self) -> None:
        assert normalise("") == ""
        assert normalise("   \n\n  ") == ""

    def test_a_markdown_hard_line_break_is_preserved(self) -> None:
        """Two trailing spaces are a line break, not stray whitespace.

        Stripping them would silently change how the document renders, which is
        exactly the quiet damage CONTRIBUTING.md rule 5 exists to prevent.
        """
        assert normalise("first line  \nsecond line\n") == "first line  \nsecond line\n"

    def test_a_long_run_of_trailing_spaces_becomes_exactly_a_hard_break(self) -> None:
        assert normalise("line     \nnext\n") == "line  \nnext\n"

    def test_trailing_spaces_before_a_blank_line_are_not_a_hard_break(self) -> None:
        assert normalise("line  \n\nnext\n") == "line\n\nnext\n"

    def test_trailing_spaces_on_the_last_line_are_not_a_hard_break(self) -> None:
        assert normalise("line  ") == "line\n"

    def test_a_fenced_code_block_is_left_completely_alone(self) -> None:
        """Whitespace inside a code block is content."""
        text = "```python\ndef f():\n    return 1  \n\n\n\n    # spaced\n```\n"

        assert normalise(text) == text

    def test_a_tilde_fence_is_also_respected(self) -> None:
        text = "~~~\na  \n\n\n\nb\n~~~\n"

        assert normalise(text) == text

    def test_text_around_a_fence_is_still_normalised(self) -> None:
        text = "before   \n\n\n\n```\ncode  \n\n\n\n```\n\n\n\nafter   \n"

        assert normalise(text) == "before\n\n```\ncode  \n\n\n\n```\n\nafter\n"

    def test_it_is_idempotent(self) -> None:
        text = "a   \n\n\n\nb\n\n```\n  keep  \n\n\n```\n"

        once = normalise(text)

        assert normalise(once) == once


class TestLinkHandler:
    @staticmethod
    def _run(text: str, **kwargs: object) -> str:
        return LinkHandler().process(text, ConvertOptions(**kwargs))  # type: ignore[arg-type]

    def test_it_is_destructive_and_stays_out_of_the_default_chain(self) -> None:
        processor = LinkHandler()

        assert processor.destructive is True
        assert processor.id not in [p.id for p in default_post_registry().default_chain()]

    def test_the_defaults_change_nothing(self) -> None:
        text = "See [the docs](https://example.com/a?b=c) and ![logo](data:image/png;base64,AAAA)."

        assert self._run(text) == text

    def test_links_can_be_flattened_to_their_text(self) -> None:
        text = "See [the docs](https://example.com/very/long/tracking?utm=1)."

        assert self._run(text, link_handling=LinkHandling.STRIP) == "See the docs."

    def test_images_can_be_reduced_to_alt_text(self) -> None:
        text = "Before ![a diagram](img.png) after."

        result = self._run(text, image_handling=ImageHandling.ALT)

        assert result == "Before a diagram after."

    def test_images_can_be_removed_entirely(self) -> None:
        text = "Before ![a diagram](img.png) after."

        result = self._run(text, image_handling=ImageHandling.STRIP)

        assert result == "Before  after."

    def test_an_image_is_not_mistaken_for_a_link(self) -> None:
        text = "![alt](i.png) and [text](l.html)"

        result = self._run(
            text, image_handling=ImageHandling.STRIP, link_handling=LinkHandling.STRIP
        )

        assert result == " and text"

    def test_a_link_title_is_removed_with_the_target(self) -> None:
        text = '[docs](https://example.com "The docs")'

        assert self._run(text, link_handling=LinkHandling.STRIP) == "docs"

    def test_a_fenced_code_block_is_left_alone(self) -> None:
        """A URL in a code sample is content, not a link to strip."""
        text = "```\n[click](https://example.com)\n```\n"

        assert self._run(text, link_handling=LinkHandling.STRIP) == text

    def test_an_inline_code_span_is_left_alone(self) -> None:
        text = "Use `[text](url)` syntax, unlike [this](https://example.com)."

        result = self._run(text, link_handling=LinkHandling.STRIP)

        assert result == "Use `[text](url)` syntax, unlike this."

    def test_a_reference_style_link_is_left_alone(self) -> None:
        """Out of scope until Phase 5; leaving it intact beats mangling it."""
        text = "See [the docs][ref].\n\n[ref]: https://example.com\n"

        assert self._run(text, link_handling=LinkHandling.STRIP) == text

    def test_an_empty_alt_image_leaves_nothing_behind_in_alt_mode(self) -> None:
        assert self._run("a ![](x.png) b", image_handling=ImageHandling.ALT) == "a  b"


class TestPostProcessorRegistry:
    def test_the_installed_entry_points_expose_every_post_processor(self) -> None:
        registry = PostProcessorRegistry()

        assert set(registry.ids()) == {
            "normalize_whitespace",
            "links",
            "strip_frontmatter",
            "aggressive_whitespace",
            "dedupe_blocks",
            "normalize_headings",
            "chunk",
            "compress",
        }

    def test_the_chain_is_ordered_by_declared_order_not_discovery_order(self) -> None:
        registry = PostProcessorRegistry()

        # Ascending `order`, which is the reserved-band layout in
        # docs/ARCHITECTURE.md: structural repair, whitespace, content
        # reduction, then reformatting.
        assert registry.ids() == (
            "strip_frontmatter",
            "normalize_whitespace",
            "aggressive_whitespace",
            "links",
            "dedupe_blocks",
            "normalize_headings",
            "chunk",
            "compress",
        )

    def test_the_default_chain_excludes_destructive_processors(self) -> None:
        """The default pipeline must not be able to damage a document."""
        registry = PostProcessorRegistry()

        assert all(not p.destructive for p in registry.default_chain())

    def test_a_plugin_written_before_the_flag_split_still_stays_out(self) -> None:
        """The reason `default_chain()` reads both flags rather than the new one.

        `Shouty` is a third-party post-processor written against the Phase 1
        contract: it sets `destructive = True` and has never heard of
        `in_default_chain`, which `BasePostProcessor` defaults to `True`. Reading
        only the new flag would have silently promoted it into the default chain
        on upgrade — a post-processor that uppercases the entire document, now
        running for people who asked for nothing.
        """
        registry = PostProcessorRegistry()
        registry.register(Shouty())

        assert Shouty.in_default_chain is True, "the legacy shape: it never set this"
        assert "shouty" not in [p.id for p in registry.default_chain()]

    def test_an_explicit_chain_runs_in_the_order_the_user_gave(self) -> None:
        """Someone naming a chain by hand means that sequence."""
        registry = PostProcessorRegistry()

        chain = registry.resolve(("links", "normalize_whitespace"))

        assert [p.id for p in chain] == ["links", "normalize_whitespace"]

    def test_an_unknown_id_lists_the_known_ones(self) -> None:
        registry = PostProcessorRegistry()

        with pytest.raises(KeyError, match="normalize_whitespace"):
            registry.resolve(("nonsense",))

    def test_an_empty_explicit_chain_runs_nothing(self) -> None:
        """Distinct from None, which means "the default chain"."""
        registry = PostProcessorRegistry()

        assert registry.resolve(()) == ()

    def test_a_third_party_post_processor_is_added_by_entry_point_alone(self) -> None:
        registry = PostProcessorRegistry()

        registry.load_from(
            [
                EntryPoint(
                    name="shouty",
                    value=f"{__name__}:Shouty",
                    group=POSTPROCESSOR_ENTRY_POINT_GROUP,
                )
            ]
        )

        assert registry.get("shouty").process("quiet", DEFAULTS) == "QUIET"

    def test_a_broken_plugin_does_not_hide_the_working_ones(self) -> None:
        registry = PostProcessorRegistry()

        registry.load_from(
            [
                EntryPoint(
                    name="broken",
                    value=f"{__name__}:no_such_attribute",
                    group=POSTPROCESSOR_ENTRY_POINT_GROUP,
                ),
                EntryPoint(
                    name="shouty",
                    value=f"{__name__}:Shouty",
                    group=POSTPROCESSOR_ENTRY_POINT_GROUP,
                ),
            ]
        )

        assert registry.ids() == ("shouty",)

    def test_both_built_ins_implement_the_protocol(self) -> None:
        for processor in (WhitespaceNormalizer(), LinkHandler()):
            assert isinstance(processor, PostProcessor)

    def test_default_registry_is_process_wide(self) -> None:
        reset_default_post_registry()
        try:
            assert default_post_registry() is default_post_registry()
        finally:
            reset_default_post_registry()


class Shouty(BasePostProcessor):
    """A third-party post-processor defined only in this test module."""

    id = "shouty"
    name = "Shouty"
    description = "uppercases everything"
    destructive = True
    order = 900

    def process(self, text: str, options: ConvertOptions) -> str:
        """Return the text in upper case.

        Args:
            text: The text to shout.
            options: Unused.

        Returns:
            The upper-cased text.
        """
        del options
        return text.upper()


class TestThePostProcessorContext:
    """Defect N2, the owner's §3.3: a post-processor can finally say something.

    The requirement that matters is not that a context arrives — it is that a
    post-processor written against the Phase 1 two-argument contract is called
    exactly as it was, and cannot tell the difference. Every test here is about
    one of those two halves.
    """

    @staticmethod
    def _registry(*processors: object) -> PostProcessorRegistry:
        registry = PostProcessorRegistry()
        for processor in processors:
            registry.register(processor)  # type: ignore[arg-type]
        return registry

    def test_a_two_parameter_processor_is_called_with_two_arguments(self) -> None:
        """The whole compatibility promise, asserted rather than described."""
        seen: list[int] = []

        class OldContract(BasePostProcessor):
            id = "old"
            name = "Old"
            description = "Written against the Phase 1 contract."

            def process(self, text: str, options: ConvertOptions) -> str:
                del options
                seen.append(2)
                return text.upper()

        processor = OldContract()
        registry = self._registry(processor)

        result = registry.run(processor, "hello", ConvertOptions(), PostProcessContext("old"))

        assert result == "HELLO"
        assert seen == [2]

    def test_a_three_parameter_processor_receives_the_context(self) -> None:
        class NewContract(BasePostProcessor):
            id = "new"
            name = "New"
            description = "Takes a context."

            def process(
                self,
                text: str,
                options: ConvertOptions,
                context: PostProcessContext | None = None,
            ) -> str:
                del options
                if context is not None:
                    context.warn("something worth saying")
                    context.note("did_something", True)
                return text

        processor = NewContract()
        registry = self._registry(processor)
        context = PostProcessContext("new")

        registry.run(processor, "hello", ConvertOptions(), context)

        assert context.warnings == ["something worth saying"]
        assert context.metadata == {"did_something": True}

    def test_a_keyword_only_context_is_recognised(self) -> None:
        class KeywordOnly(BasePostProcessor):
            id = "kw"
            name = "Keyword"
            description = "Declares context keyword-only."

            def process(
                self,
                text: str,
                options: ConvertOptions,
                *,
                context: PostProcessContext | None = None,
            ) -> str:
                del options
                if context is not None:
                    context.note("reached", True)
                return text

        registry = self._registry()

        assert registry.wants_context(KeywordOnly())

    def test_a_star_args_processor_is_not_given_a_context(self) -> None:
        """`*args` swallows a context rather than using it.

        A processor written that way has declared nothing, and handing it an
        argument it will silently drop is worse than not handing it one: the
        author would see no error and no context, and have nothing to debug.
        """

        class Sloppy:
            id = "sloppy"
            name = "Sloppy"
            description = "Takes anything."
            destructive = False
            in_default_chain = False
            order = 500

            def process(self, *args: object) -> str:
                return str(args[0])

        registry = self._registry()

        assert not registry.wants_context(Sloppy())

    def test_the_answer_is_cached(self) -> None:
        class Counting(BasePostProcessor):
            id = "counting"
            name = "Counting"
            description = "For the cache test."

            def process(self, text: str, options: ConvertOptions) -> str:
                del options
                return text

        processor = Counting()
        registry = self._registry(processor)

        first = registry.wants_context(processor)
        second = registry.wants_context(processor)

        assert first is second is False
        assert id(processor) in registry._wants_context  # the cache, by name


class TestThePipelineCollectsWhatAPostProcessorSays:
    def test_a_warning_is_attributed_and_reaches_the_result(self) -> None:
        class Noisy(BasePostProcessor):
            id = "noisy"
            name = "Noisy"
            description = "Warns."
            in_default_chain = True

            def process(
                self,
                text: str,
                options: ConvertOptions,
                context: PostProcessContext | None = None,
            ) -> str:
                del options
                if context is not None:
                    context.warn("there was nothing to do")
                return text

        posts = PostProcessorRegistry()
        posts.register(Noisy())
        pipeline = Pipeline(post_processors=posts)

        result = pipeline.run(
            Source.from_text("some text", name="a.md"), ConvertOptions(tokenizer="bytes")
        )

        assert "noisy: there was nothing to do" in result.warnings

    def test_a_note_is_namespaced_by_processor(self) -> None:
        """Two processors noting the same key must not overwrite each other."""

        def maker(processor_id: str) -> object:
            class Noting(BasePostProcessor):
                id = processor_id
                name = processor_id
                description = "Notes a ratio."
                in_default_chain = True

                def process(
                    self,
                    text: str,
                    options: ConvertOptions,
                    context: PostProcessContext | None = None,
                ) -> str:
                    del options
                    if context is not None:
                        context.note("ratio", processor_id)
                    return text

            return Noting()

        posts = PostProcessorRegistry()
        posts.register(maker("first"))  # type: ignore[arg-type]
        posts.register(maker("second"))  # type: ignore[arg-type]
        pipeline = Pipeline(post_processors=posts)

        result = pipeline.run(
            Source.from_text("some text", name="a.md"), ConvertOptions(tokenizer="bytes")
        )

        assert result.metadata["post.first.ratio"] == "first"
        assert result.metadata["post.second.ratio"] == "second"
