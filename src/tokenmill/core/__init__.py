"""Core architecture: the data model, the protocol, the registry and the pipeline.

This is the architecture contract from ``docs/DEVELOPMENT_PLAN.md`` §1. Backends,
post-processors, tokenizers, the CLI and the Phase 8 GUI all build against it,
so a change here is a breaking change requiring owner sign-off.
"""

from __future__ import annotations

__all__: list[str] = []
