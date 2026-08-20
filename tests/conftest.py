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
    """Return the sample repository, restoring anything git could not carry.

    Two parts of this fixture cannot live in the tokenmill repository:

    * ``.git`` — git stores a nested repository as a gitlink and keeps none of
      its contents, so clones would end up with an empty directory.
    * ``secrets.env`` — the fixture's own ``.gitignore`` lists it, and git
      applies nested ignore files to the outer repository too, so it is never
      committed. Repo-ingestion backends must be catchable leaking it.

    Both are recreated here on demand. Recreating ``.git`` is deterministic: the
    commit dates are pinned, so the HEAD hash matches the one recorded in
    ``ground_truth.json``.
    """
    root = fixture_dir / "sample_repo"
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from make_fixtures import ensure_sample_repo_git, ensure_sample_repo_ignored_files
    except ImportError:  # pragma: no cover - only when scripts/ is absent
        pytest.skip("scripts/make_fixtures.py is not importable")

    # Both are uncommittable for the same reason and are restored the same way:
    # git stores a nested .git as a gitlink, and the fixture's own .gitignore
    # hides secrets.env from the outer repository too.
    ensure_sample_repo_ignored_files(root)
    if not (root / ".git").is_dir():
        ensure_sample_repo_git(root)
    return root
