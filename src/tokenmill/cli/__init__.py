"""The tokenmill command line.

The CLI is a presentation layer and nothing more: it parses arguments, calls the
public library API, and formats what comes back. Every capability it offers is
reachable from :mod:`tokenmill` directly, which is what keeps the Phase 8 GUI
honest — it will call the same API rather than reimplementing anything here.
"""

from __future__ import annotations

__all__: list[str] = []
