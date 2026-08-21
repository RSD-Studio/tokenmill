"""Smoke tests that must pass with only the default (core) dependencies installed."""

from __future__ import annotations

import importlib
import re
import subprocess
import sys

# Snapshot sys.modules, import tokenmill, and report what that import *added*.
# Comparing a delta rather than a stdlib allow-list keeps the test honest in
# environments that inject their own modules (coverage's sitecustomize, for one).
_IMPORT_DELTA_PROBE = """
import sys

before = set(sys.modules)
import tokenmill  # noqa: F401
added = sorted(
    name
    for name in set(sys.modules) - before
    if not name.startswith(("tokenmill", "_"))
)
print(",".join(added))
"""


def test_version_is_pep440_ish() -> None:
    tokenmill = importlib.import_module("tokenmill")
    assert re.fullmatch(r"\d+\.\d+\.\d+([abrc.\-+\w]*)?", tokenmill.__version__)


def test_public_surface_is_explicit() -> None:
    """`__all__` is the API. Anything not in it is not promised to anybody."""
    tokenmill = importlib.import_module("tokenmill")

    assert tokenmill.__all__ == sorted(tokenmill.__all__), "keep __all__ sorted"
    for name in tokenmill.__all__:
        assert hasattr(tokenmill, name), f"__all__ names {name}, which does not exist"


def test_the_public_api_covers_what_a_caller_needs() -> None:
    """A one-call conversion plus the types needed to drive and read it."""
    tokenmill = importlib.import_module("tokenmill")

    expected = {
        "convert",
        "Pipeline",
        "Source",
        "ConvertOptions",
        "ConversionResult",
        "TokenCount",
        "BackendInfo",
        "Converter",
        "BaseConverter",
        "Registry",
        "ConversionError",
        "TokenmillError",
    }

    assert expected <= set(tokenmill.__all__)


def test_import_pulls_no_third_party_dependency() -> None:
    """`import tokenmill` must work on a machine with nothing else installed.

    Backends may depend on anything they like, but they import lazily. If this
    test ever fails, a heavy or copyleft dependency has leaked into the import
    path and `pip install tokenmill` is no longer light.
    """
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _IMPORT_DELTA_PROBE],
        check=True,
        capture_output=True,
        text=True,
    )
    added = [name for name in result.stdout.strip().split(",") if name]
    stdlib = sys.stdlib_module_names
    third_party = sorted({name.split(".")[0] for name in added} - set(stdlib))
    assert third_party == [], f"importing tokenmill pulled in third-party modules: {third_party}"
