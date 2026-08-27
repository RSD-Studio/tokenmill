"""The GUI may only call the public library API, asserted over the import graph.

`docs/DEVELOPMENT_PLAN.md` names this phase's risk — *GUI logic creeping into
the UI layer* — and states the mitigation as a rule: the GUI may only call the
public library API. A rule that lives in a docstring is a habit. This makes it a
property of the code that fails when it stops being true.

The check is deliberately structural rather than behavioural. A test that
exercised the UI would pass whether or not `app.py` reached around `api.py`,
because both routes produce the same answer today. What goes wrong later is that
someone adds a conversion decision to a click handler where the CLI cannot reach
it, and the two interfaces drift. Parsing the imports catches that on the day it
is written.

These run everywhere, including where the `gui` extra is absent: the module is
read as text, never imported.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tokenmill.core.licensing import imported_top_level_modules

GUI = Path(__file__).resolve().parents[2] / "src" / "tokenmill" / "gui"

#: What `app.py` is allowed to import from tokenmill.
#:
#: `tokenmill.gui.api` is the surface. `tokenmill.core.models` is on the list for
#: one reason: constructing a `Source` is how the user's file, URL or pasted text
#: enters the system, and it is a data-model call rather than a conversion
#: decision. `tokenmill.core.registry` is there for the one `supports()` question
#: the compare panel asks. Nothing else.
_ALLOWED_IN_APP = {
    "tokenmill.gui",
    "tokenmill.gui.api",
    "tokenmill.gui.batch",
    "tokenmill.core.models",
    "tokenmill.core.registry",
}


def _tokenmill_imports(path: Path) -> set[str]:
    """Return every ``tokenmill.*`` module a file imports, at any nesting depth.

    Args:
        path: The file to scan.

    Returns:
        The dotted module names.
    """
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            if node.module.startswith("tokenmill"):
                found.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("tokenmill"):
                    found.add(alias.name)
    return found


class TestTheGuiCallsOnlyItsApi:
    def test_the_ui_layer_imports_nothing_it_should_not(self) -> None:
        """`app.py` is layout and event handlers, and that is checkable."""
        reached = _tokenmill_imports(GUI / "app.py")
        forbidden = reached - _ALLOWED_IN_APP

        assert not forbidden, (
            f"src/tokenmill/gui/app.py imports {sorted(forbidden)}. The GUI may "
            f"only call tokenmill.gui.api; anything it needs that the api layer "
            f"cannot express belongs in the api layer, where the CLI and the "
            f"tests can reach it too"
        )

    def test_the_ui_layer_does_not_reach_into_the_pipeline_or_the_backends(self) -> None:
        """The specific failure this is watching for, named."""
        reached = _tokenmill_imports(GUI / "app.py")

        for module in reached:
            assert not module.startswith("tokenmill.backends"), module
            assert not module.startswith("tokenmill.post"), module
            assert not module.startswith("tokenmill.fidelity"), module
            assert module != "tokenmill.core.pipeline", module

    def test_the_api_layer_imports_no_ui_toolkit(self) -> None:
        """So it runs, and is tested, on an install with no `gui` extra.

        This is what lets `test_gui_api.py` exercise every GUI action on all
        nine CI cells rather than only where nicegui happens to be installed.
        """
        for name in ("api.py", "batch.py"):
            imported = imported_top_level_modules(GUI / name)
            assert "nicegui" not in imported, f"{name} imports nicegui"
            assert "fastapi" not in imported, f"{name} imports fastapi"

    def test_the_batch_runner_does_not_import_the_ui_either(self) -> None:
        """The queue is library code that a headless caller can use."""
        reached = _tokenmill_imports(GUI / "batch.py")

        assert "tokenmill.gui.app" not in reached

    @pytest.mark.parametrize("name", ["api.py", "batch.py", "app.py", "__init__.py"])
    def test_every_gui_module_is_importable_as_source(self, name: str) -> None:
        """Guard the guard: a scan of a file that does not exist passes."""
        assert (GUI / name).is_file()


class TestTheCliDegradesWithoutTheExtra:
    """`tokenmill gui` on a core-only install is a message, not a traceback."""

    def test_a_missing_nicegui_gives_the_install_command(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulated, because the dev environment has the extra installed.

        Verified for real against a core-only virtualenv on 2026-08-26, which
        printed exactly these two lines; this is what keeps it true.
        """
        import builtins

        from typer.testing import CliRunner

        from tokenmill.cli.main import app

        real_import = builtins.__import__

        def refuse(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("tokenmill.gui.app") or name == "nicegui":
                raise ImportError("no nicegui here")
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", refuse)
        result = CliRunner().invoke(app, ["gui"])

        assert result.exit_code == 1
        assert "Traceback" not in result.output
        assert 'pip install "tokenmill[gui]"' in result.output
