"""Helpers that are deliberately unremarkable."""

from __future__ import annotations

from collections.abc import Iterable


def total_size(widgets: Iterable[object]) -> int:
    """Sum the ``size`` attribute of every widget in ``widgets``."""
    return sum(getattr(widget, "size", 0) for widget in widgets)
