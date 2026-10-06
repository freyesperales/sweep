"""Shared pytest fixtures: a realistic multi-ecosystem fixture tree."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest


def _write(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"\0" * size)


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    """Build a project tree with several reclaimable artifacts.

    Layout:
        root/
          web/            (package.json)      node_modules  ~3000 B
          api/            (pyproject.toml)     .venv         ~1500 B
            __pycache__/                                     ~100 B
          rustapp/        (Cargo.toml)         target        ~5000 B
          plainbuild/     (no manifest)        build         (NOT matched)
          src/ (real source, must be untouched)
    """
    root = tmp_path / "projects"

    # Node project with node_modules (always matched, no marker needed).
    _write(root / "web" / "package.json", 20)
    _write(root / "web" / "node_modules" / "left-pad" / "index.js", 1000)
    _write(root / "web" / "node_modules" / "react" / "react.js", 2000)

    # Python project with .venv + __pycache__.
    _write(root / "api" / "pyproject.toml", 20)
    _write(root / "api" / ".venv" / "lib" / "site.py", 1500)
    _write(root / "api" / "__pycache__" / "mod.cpython-311.pyc", 100)
    _write(root / "api" / "app.py", 50)  # real source

    # Rust project; `target` only matches next to Cargo.toml.
    _write(root / "rustapp" / "Cargo.toml", 20)
    _write(root / "rustapp" / "target" / "debug" / "app.exe", 5000)
    _write(root / "rustapp" / "src" / "main.rs", 40)  # real source

    # A generic `build` dir with NO build manifest -> must NOT match.
    _write(root / "plainbuild" / "build" / "artifact.bin", 9999)

    return root


@pytest.fixture()
def aged_tree(tree: Path) -> Path:
    """Make the rust `target` old (120 days) and node_modules fresh (1 day)."""
    now = time.time()
    old = now - 120 * 86400
    fresh = now - 1 * 86400

    target_file = tree / "rustapp" / "target" / "debug" / "app.exe"
    os.utime(target_file, (old, old))
    os.utime(tree / "rustapp" / "target" / "debug", (old, old))
    os.utime(tree / "rustapp" / "target", (old, old))

    for f in (tree / "web" / "node_modules").rglob("*"):
        os.utime(f, (fresh, fresh))
    os.utime(tree / "web" / "node_modules", (fresh, fresh))
    return tree
