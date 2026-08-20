"""Core widget implementation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Widget:
    """A widget with a name and an optional size."""

    name: str
    size: int = 1

    def render(self) -> str:
        """Return the widget's textual representation."""
        return f"<{self.name} size={self.size}>"

    def scaled(self, factor: int) -> Widget:
        """Return a copy of this widget scaled by ``factor``."""
        if factor <= 0:
            raise ValueError("factor must be positive")
        return Widget(self.name, self.size * factor)
