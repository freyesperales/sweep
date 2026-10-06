"""Tests for the core scan/match/size/age/filter logic."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from sweep import core
from sweep.core import (
    STALE_THRESHOLD_SECONDS,
    directory_size,
    filter_findings,
    scan,
)


def _by_name(stats) -> dict[str, core.Finding]:
    return {f.path.name + "@" + f.path.parent.name: f for f in stats.findings}


def test_scan_matches_expected_artifacts(tree: Path) -> None:
    stats = scan(tree)
    names = {f.path.name for f in stats.findings}
    assert "node_modules" in names
    assert ".venv" in names
    assert "__pycache__" in names
    assert "target" in names  # matched: Cargo.toml sibling present


def test_scan_respects_markers(tree: Path) -> None:
    """A `build` dir without a build manifest must NOT be matched."""
    stats = scan(tree)
    build_hits = [
        f for f in stats.findings
        if f.path.name == "build" and f.path.parent.name == "plainbuild"
    ]
    assert build_hits == []


def test_scan_does_not_match_source(tree: Path) -> None:
    paths = {str(f.path) for f in scan(tree).findings}
    assert str(tree / "api" / "app.py") not in paths
    assert str(tree / "rustapp" / "src") not in paths


def test_sizes_and_sorted_desc(tree: Path) -> None:
    stats = scan(tree)
    sizes = [f.size_bytes for f in stats.findings]
    assert sizes == sorted(sizes, reverse=True)
    # target (5000) should be the largest, node_modules (3000) next.
    assert stats.findings[0].path.name == "target"
    assert stats.findings[0].size_bytes == 5000


def test_ecosystem_tagging(tree: Path) -> None:
    stats = scan(tree)
    eco = {f.path.name: f.ecosystem for f in stats.findings}
    assert eco["node_modules"] == "node"
    assert eco[".venv"] == "python"
    assert eco["target"] == "rust"


def test_age_and_stale(aged_tree: Path) -> None:
    now = time.time()
    stats = scan(aged_tree)
    target = next(f for f in stats.findings if f.path.name == "target")
    nm = next(f for f in stats.findings if f.path.name == "node_modules")
    assert target.is_stale(now)  # 120 days old
    assert not nm.is_stale(now)  # 1 day old
    assert target.age_seconds(now) >= STALE_THRESHOLD_SECONDS


def test_directory_size_counts_files(tree: Path) -> None:
    total, count, mtime, error = directory_size(tree / "web" / "node_modules")
    assert total == 3000
    assert count == 2
    assert error is None
    assert mtime > 0


def test_does_not_descend_into_matched_dir(tmp_path: Path) -> None:
    """A nested node_modules inside node_modules is not reported separately."""
    root = tmp_path / "p"
    inner = root / "node_modules" / "pkg" / "node_modules"
    inner.mkdir(parents=True)
    (root / "node_modules" / "a.js").write_bytes(b"x" * 10)
    (inner / "b.js").write_bytes(b"y" * 10)
    stats = scan(root)
    nm = [f for f in stats.findings if f.path.name == "node_modules"]
    assert len(nm) == 1
    assert nm[0].size_bytes == 20  # includes the nested file


def test_filter_min_size(tree: Path) -> None:
    now = time.time()
    stats = scan(tree)
    filtered = filter_findings(stats.findings, now=now, min_size=2000)
    sizes = {f.path.name: f.size_bytes for f in filtered}
    assert "target" in sizes and "node_modules" in sizes
    assert ".venv" not in sizes  # 1500 < 2000
    assert "__pycache__" not in sizes


def test_filter_older_than(aged_tree: Path) -> None:
    now = time.time()
    stats = scan(aged_tree)
    filtered = filter_findings(
        stats.findings, now=now, older_than_seconds=90 * 86400
    )
    names = {f.path.name for f in filtered}
    assert "target" in names       # 120 days
    assert "node_modules" not in names  # 1 day


def test_filter_ecosystem(tree: Path) -> None:
    now = time.time()
    stats = scan(tree)
    filtered = filter_findings(
        stats.findings, now=now, ecosystems=frozenset({"python"})
    )
    assert all(f.ecosystem == "python" for f in filtered)
    assert {f.path.name for f in filtered} == {".venv", "__pycache__"}


def test_scan_missing_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        scan(tmp_path / "does-not-exist")


def test_scan_not_a_directory(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("hi")
    with pytest.raises(NotADirectoryError):
        scan(f)


def test_scan_handles_empty(tmp_path: Path) -> None:
    stats = scan(tmp_path)
    assert stats.findings == []
    assert stats.total_bytes == 0


@pytest.mark.skipif(
    not hasattr(os, "symlink"), reason="symlinks unsupported"
)
def test_symlinks_not_followed(tmp_path: Path) -> None:
    root = tmp_path / "p"
    (root / "web").mkdir(parents=True)
    (root / "web" / "package.json").write_bytes(b"{}")
    real_nm = root / "web" / "node_modules"
    real_nm.mkdir()
    (real_nm / "a.js").write_bytes(b"x" * 100)
    # A symlink that points back up would cause an infinite loop if followed.
    link = root / "web" / "node_modules" / "loop"
    try:
        os.symlink(root, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted")
    stats = scan(root)  # must terminate
    nm = [f for f in stats.findings if f.path.name == "node_modules"]
    assert len(nm) == 1
