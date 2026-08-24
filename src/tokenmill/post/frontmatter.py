"""Front-matter stripping.

A static-site generator's YAML or TOML front matter is metadata for the
generator, not content for a model. It is cheap to remove and it is at the top
of the document, where it competes with the material a model reads first.

**Destructive**, because the front matter is content the user may have wanted —
a title, an author, a canonical URL — and once it is gone the document cannot
say where it came from. Off by default, like every destructive step.

Only a block at the very start of the document is removed. A `---` in the middle
of a Markdown file is a thematic break, and a post-processor that deleted
everything up to the next one would silently swallow the document.
"""

from __future__ import annotations

import re
from typing import Final

from tokenmill.core.models import ConvertOptions
from tokenmill.post.base import BasePostProcessor

__all__ = ["FrontMatterStripper"]

#: The delimiters that open and close a front-matter block, mapped to what
#: closes them. YAML uses ``---``; TOML front matter uses ``+++``.
_DELIMITERS: Final = {"---": "---", "+++": "+++"}

#: A closing delimiter line.
_CLOSE_RE: Final = re.compile(r"^(?P<delimiter>-{3,}|\+{3,})\s*$")


class FrontMatterStripper(BasePostProcessor):
    """Removes a YAML or TOML front-matter block from the top of a document.

    Attributes:
        id: ``strip_frontmatter``.
        name: Display name.
        description: One-line summary.
        destructive: True — the metadata is gone.
        order: 50, in the structural-repair band, so everything downstream sees
            the document without its header.
    """

    id = "strip_frontmatter"
    name = "Strip front matter"
    description = (
        "Remove a leading YAML (---) or TOML (+++) front-matter block. "
        "Metadata for a site generator, not content for a model."
    )
    destructive = True
    order = 50

    def process(self, text: str, options: ConvertOptions) -> str:  # noqa: ARG002
        """Remove the leading front-matter block, if there is one.

        Args:
            text: The document.
            options: Unused; this post-processor takes no settings.

        Returns:
            The document without its front matter, or unchanged when it has
            none or when the block is never closed. An unterminated block is
            left alone deliberately: the alternative is deleting the whole
            file because its first line happened to be a thematic break.
        """
        lines = text.split("\n")
        first = 0
        # A leading blank line or two before the delimiter is common enough in
        # converter output to be worth tolerating.
        while first < len(lines) and not lines[first].strip():
            first += 1
        if first >= len(lines):
            return text

        opener = lines[first].strip()
        if opener not in _DELIMITERS:
            return text

        for index in range(first + 1, len(lines)):
            match = _CLOSE_RE.match(lines[index].strip())
            if match and match.group("delimiter")[0] == opener[0]:
                remainder = lines[index + 1 :]
                while remainder and not remainder[0].strip():
                    remainder.pop(0)
                return "\n".join(remainder)
        return text
