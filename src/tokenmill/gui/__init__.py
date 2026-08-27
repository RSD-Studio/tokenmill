"""The graphical interface: a NiceGUI front end over the public library API.

Three modules, and the split is the phase's stated risk mitigation rather than
tidiness:

* :mod:`tokenmill.gui.api` — every action the interface can perform, as
  functions. Imports no UI toolkit, so it runs and is tested on a core-only
  install.
* :mod:`tokenmill.gui.batch` — the queue, on one worker thread. See its
  docstring for why one and not a pool; the short version is defect D2.
* :mod:`tokenmill.gui.app` — layout and event handlers, and nothing else.

``docs/DEVELOPMENT_PLAN.md`` names this phase's risk as *GUI logic creeping into
the UI layer*, and its mitigation as *the GUI may only call the public library
API*. ``tests/unit/test_gui_boundary.py`` asserts that as a property of the
import graph rather than as a habit.
"""

from __future__ import annotations

__all__: list[str] = []
