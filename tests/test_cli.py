"""Tests for CLI behavior, dry-run safety, and delete routing to trash."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sweep import cli, core, trash


def _count_artifacts(tree: Path) -> int:
    return len(core.scan(tree).findings)


def test_json_mode_lists_and_deletes_nothing(tree: Path, capsys) -> None:
    before = _count_artifacts(tree)
    rc = cli.main([str(tree), "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["count"] >= 3
    assert payload["total_reclaimable_bytes"] > 0
    names = {item["rule"] for item in payload["findings"]}
    assert "node_modules" in names
    # Nothing deleted.
    assert _count_artifacts(tree) == before


def test_dry_run_deletes_nothing(tree: Path, capsys) -> None:
    before = _count_artifacts(tree)
    rc = cli.main([str(tree), "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Dry run: nothing was deleted." in out
    assert _count_artifacts(tree) == before
    # Directories still physically exist.
    assert (tree / "web" / "node_modules").exists()
    assert (tree / "rustapp" / "target").exists()


def test_min_size_filter_in_json(tree: Path, capsys) -> None:
    rc = cli.main([str(tree), "--json", "--min-size", "2000"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    sizes = {i["rule"]: i["size_bytes"] for i in payload["findings"]}
    assert ".venv" not in sizes  # 1500 bytes filtered out
    assert "target" in sizes


def test_older_than_filter_in_json(aged_tree: Path, capsys) -> None:
    rc = cli.main([str(aged_tree), "--json", "--older-than", "90d"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    names = {i["rule"] for i in payload["findings"]}
    assert "target" in names
    assert "node_modules" not in names


def test_bad_min_size_returns_error(tree: Path, capsys) -> None:
    rc = cli.main([str(tree), "--min-size", "banana"])
    assert rc == 2
    assert "min-size" in capsys.readouterr().err


def test_unknown_ecosystem_returns_error(tree: Path, capsys) -> None:
    rc = cli.main([str(tree), "--ecosystem", "cobol", "--json"])
    assert rc == 2
    assert "unknown ecosystem" in capsys.readouterr().err


def test_missing_path_returns_error(tmp_path: Path, capsys) -> None:
    rc = cli.main([str(tmp_path / "nope"), "--json"])
    assert rc == 2
    assert "does not exist" in capsys.readouterr().err


def test_yes_routes_delete_to_trash(tree: Path, monkeypatch, capsys) -> None:
    """--yes must call the trash layer, never a hard delete, for each item."""
    trashed: list[str] = []

    def fake_send(path):
        trashed.append(str(path))
        # Do NOT actually delete; we only assert routing.

    monkeypatch.setattr(trash, "send_to_trash", fake_send)

    before = _count_artifacts(tree)
    rc = cli.main([str(tree), "--yes"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Reclaimed" in out
    # Every matched artifact was routed to trash.
    assert len(trashed) == before
    assert any("node_modules" in p for p in trashed)
    # Because our fake didn't delete, dirs still exist (proves we mocked it).
    assert (tree / "web" / "node_modules").exists()


def test_yes_with_filter_only_trashes_matches(
    tree: Path, monkeypatch, capsys
) -> None:
    trashed: list[str] = []
    monkeypatch.setattr(
        trash, "send_to_trash", lambda p: trashed.append(str(p))
    )
    rc = cli.main([str(tree), "--yes", "--min-size", "2000"])
    assert rc == 0
    # Only target (5000) and node_modules (3000) qualify.
    assert len(trashed) == 2
    assert all(
        ("target" in p or "node_modules" in p) for p in trashed
    )


def test_delete_finding_calls_trash(monkeypatch, tree: Path) -> None:
    captured: list[str] = []
    monkeypatch.setattr(
        trash, "send_to_trash", lambda p: captured.append(str(p))
    )
    stats = core.scan(tree)
    core.delete_finding(stats.findings[0])
    assert captured == [str(stats.findings[0].path)]
