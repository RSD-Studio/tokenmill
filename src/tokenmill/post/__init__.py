"""Post-processors: the ordered chain applied to a converter's output.

Registered through the ``tokenmill.postprocessors`` entry point group. Anything
that can lose information declares itself destructive and stays out of the
default chain.
"""

from __future__ import annotations

__all__: list[str] = []
