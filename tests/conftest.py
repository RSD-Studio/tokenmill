"""Shared pytest fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


@pytest.fixture(scope="session")
def fixture_dir() -> Path:
    """Return the directory holding the synthetic test corpus."""
    if not (FIXTURE_DIR / "ground_truth.json").exists():
        pytest.skip("test corpus not generated; run scripts/make_fixtures.py")
    return FIXTURE_DIR


@pytest.fixture(scope="session")
def ground_truth(fixture_dir: Path) -> dict[str, Any]:
    """Return the ground-truth manifest keyed by fixture name."""
    manifest: dict[str, Any] = json.loads(
        (fixture_dir / "ground_truth.json").read_text(encoding="utf-8")
    )
    fixtures: dict[str, Any] = manifest["fixtures"]
    return fixtures


@pytest.fixture(scope="session")
def sample_repo(fixture_dir: Path) -> Path:
    """Return the sample repository, materialising its ``.git`` if absent.

    The fixture's working files are committed but its ``.git`` directory is not,
    because git stores a nested repository as a gitlink and clones would end up
    with an empty directory. Recreating it is deterministic: the commit dates
    are pinned, so the HEAD hash matches the one recorded in
    ``ground_truth.json``.
    """
    root = fixture_dir / "sample_repo"
    if not (root / ".git").is_dir():
        sys.path.insert(0, str(SCRIPTS_DIR))
        try:
            from make_fixtures import ensure_sample_repo_git
        except ImportError:  # pragma: no cover - only when scripts/ is absent
            pytest.skip("scripts/make_fixtures.py is not importable")
        ensure_sample_repo_git(root)
    return root
