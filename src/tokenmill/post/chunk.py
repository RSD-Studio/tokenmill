"""Token-aware chunking, via Chonkie.

Splitting a long document into model-sized pieces is the last thing that
happens to it before it reaches a prompt, which is why chunking sits at order
700 — after every reduction and before compression.

**Chonkie is behind the `chunk` extra**, not in the core install. The plan's
§1.6 lists it in core and this is a deliberate departure, measured rather than
argued: on 2026-08-24 it added 10 packages and took a core install from 126 MB
to 196 MB of `lib/`, almost all of it numpy. Defect D4 records that core already
grew 2.3x in Phase 3 without anyone deciding that was acceptable. The owner was
asked and chose the extra.

**The chunk size is in the run's own unit.** Chonkie's `ByteTokenizer` was
checked against tokenmill's `bytes` counter on multibyte text and emoji and
agrees exactly, so `--tokenizer bytes --chunk-size 2000` means 2,000 UTF-8
bytes, the same unit every other number in the report is in. Under a real model
tokenizer the id is handed to Chonkie to resolve, which needs the vocabulary
download that tokenizer needs anyway.

**Why this is marked destructive**, when it deletes nothing: `destructive` is
the only mechanism that keeps a post-processor out of the default chain, and a
conversion that silently grew chunk boundaries nobody asked for would be exactly
the surprise the flag exists to prevent. That does stretch the flag's stated
meaning — "can lose information the user might have wanted" — and the stretch is
recorded in `PROGRESS.md` as a question for the owner rather than papered over.
"""

from __future__ import annotations

from typing import Any, Final

from tokenmill.core.errors import BackendUnavailable
from tokenmill.core.models import ConvertOptions
from tokenmill.post.base import BasePostProcessor

__all__ = ["DEFAULT_CHUNK_SIZE", "DEFAULT_SEPARATOR", "Chunker"]

#: Chunk size when the user names none, in the run's tokenizer's unit.
DEFAULT_CHUNK_SIZE: Final = 2048

#: What goes between chunks. An HTML comment: invisible when the Markdown is
#: rendered, trivially machine-splittable, and it says which chunk is which so
#: a truncated prompt is recognisable as truncated.
DEFAULT_SEPARATOR: Final = "\n\n<!-- tokenmill:chunk {index}/{total} -->\n\n"

#: tokenmill's measurement units, mapped onto Chonkie's equivalents. Anything
#: not named here is passed to Chonkie as a string for it to resolve, which is
#: how a real model tokenizer gets used.
_NATIVE_TOKENIZERS: Final = {"bytes": "ByteTokenizer"}


class Chunker(BasePostProcessor):
    """Splits a document into token-sized chunks, marked in place.

    Attributes:
        id: ``chunk``.
        name: Display name.
        description: One-line summary.
        destructive: True — see the module docstring; it changes the document's
            shape and must not be in the default chain.
        order: 700, the chunking band.
    """

    id = "chunk"
    name = "Chunk"
    description = (
        "Split into token-sized chunks separated by a marker comment. Sizes are "
        "in the run's tokenizer's unit. Needs `pip install tokenmill[chunk]`."
    )
    destructive = True
    order = 700

    def process(self, text: str, options: ConvertOptions) -> str:
        """Split ``text`` into chunks and rejoin them with a marker.

        Args:
            text: The document to chunk.
            options: Read for ``tokenizer`` and for ``extra['chunk_size']``,
                ``extra['chunk_overlap']``, ``extra['chunk_separator']`` and
                ``extra['chunker']``.

        Returns:
            The chunks, separated by the marker. A document that already fits
            in one chunk comes back unchanged, with no marker at all — a
            separator that appeared only to say "this was not split" would be
            pure cost.

        Raises:
            BackendUnavailable: If Chonkie is not installed, or cannot resolve
                the run's tokenizer. Raising beats returning the text unchanged:
                Phase 1 settled that a flag which silently does nothing is worse
                than no flag.
        """
        if not text.strip():
            return text

        chunker = self._build(options)
        chunks = [chunk.text for chunk in chunker(text)]
        if len(chunks) <= 1:
            return text

        separator = options.extra.get("chunk_separator", DEFAULT_SEPARATOR)
        if not isinstance(separator, str):
            separator = DEFAULT_SEPARATOR

        out = [chunks[0]]
        for index, chunk in enumerate(chunks[1:], start=2):
            out.append(separator.format(index=index, total=len(chunks)))
            out.append(chunk)
        return "".join(out)

    def _build(self, options: ConvertOptions) -> Any:
        """Construct the Chonkie chunker for this run.

        Args:
            options: Supplies the tokenizer and the chunking settings.

        Returns:
            The chunker, ready to call.

        Raises:
            BackendUnavailable: If Chonkie is absent or the tokenizer is one it
                cannot resolve.
        """
        try:
            import chonkie
        except ImportError as exc:
            msg = "chunking needs Chonkie, which is not installed"
            raise BackendUnavailable(
                msg, hint='install it with `pip install "tokenmill[chunk]"`'
            ) from exc

        size = options.extra.get("chunk_size", DEFAULT_CHUNK_SIZE)
        chunk_size = size if isinstance(size, int) and size > 0 else DEFAULT_CHUNK_SIZE
        overlap = options.extra.get("chunk_overlap", 0)
        chunk_overlap = overlap if isinstance(overlap, int) and overlap >= 0 else 0

        native = _NATIVE_TOKENIZERS.get(options.tokenizer)
        tokenizer: Any = getattr(chonkie, native)() if native else options.tokenizer

        style = options.extra.get("chunker", "recursive")
        try:
            if style == "token":
                return chonkie.TokenChunker(
                    tokenizer=tokenizer, chunk_size=chunk_size, chunk_overlap=chunk_overlap
                )
            # Recursive by default: it splits on paragraph, then sentence, then
            # word boundaries, so a chunk boundary lands between blocks rather
            # than through the middle of one. `RESEARCH.md` Category 7's rule —
            # keep structure, strip boilerplate — applies to splitting too.
            return chonkie.RecursiveChunker(tokenizer=tokenizer, chunk_size=chunk_size)
        except Exception as exc:
            msg = f"Chonkie could not chunk with tokenizer {options.tokenizer!r}: {exc}"
            raise BackendUnavailable(
                msg,
                hint="use --tokenizer bytes, which needs no download, or install "
                "the vocabulary this tokenizer requires",
            ) from exc
