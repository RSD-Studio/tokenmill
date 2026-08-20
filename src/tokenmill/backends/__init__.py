"""Built-in backend adapters.

Backends are registered through the ``tokenmill.backends`` entry point group
declared in ``pyproject.toml``, exactly as a third-party plugin would be. This
package deliberately imports none of them: importing a backend costs whatever
its dependency costs, and the registry loads them lazily on first use.

See ``docs/ADDING_A_BACKEND.md`` for how to write one.
"""

from __future__ import annotations

__all__: list[str] = []
