"""Tests for the trash layer (without actually touching the OS trash)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sweep import trash


def test_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(trash.TrashError):
        trash.send_to_trash(tmp_path / "nope")


def test_prefers_send2trash(monkeypatch, tmp_path: Path) -> None:
    """When _via_send2trash succeeds, no platform fallback is invoked."""
    victim = tmp_path / "victim"
    victim.mkdir()

    called = {"send2trash": False, "fallback": False}

    def fake_via(path):
        called["send2trash"] = True
        return True

    monkeypatch.setattr(trash, "_via_send2trash", fake_via)
    monkeypatch.setattr(
        trash, "_windows_recycle",
        lambda p: called.__setitem__("fallback", True),
    )
    monkeypatch.setattr(
        trash, "_freedesktop_trash",
        lambda p: called.__setitem__("fallback", True),
    )
    monkeypatch.setattr(
        trash, "_macos_trash",
        lambda p: called.__setitem__("fallback", True),
    )

    trash.send_to_trash(victim)
    assert called["send2trash"] is True
    assert called["fallback"] is False
    # Our fake did not delete it.
    assert victim.exists()


def test_falls_back_when_send2trash_absent(monkeypatch, tmp_path: Path) -> None:
    victim = tmp_path / "victim2"
    victim.mkdir()
    fell_back = {"yes": False}

    monkeypatch.setattr(trash, "_via_send2trash", lambda p: False)
    monkeypatch.setattr(trash.sys, "platform", "linux")
    monkeypatch.setattr(
        trash, "_freedesktop_trash",
        lambda p: fell_back.__setitem__("yes", True),
    )
    trash.send_to_trash(victim)
    assert fell_back["yes"] is True
