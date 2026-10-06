"""Reversible delete: route to the OS trash/recycle bin.

Prefers the ``send2trash`` package when installed (handles Windows Recycle Bin,
macOS Trash, and the freedesktop.org trash spec correctly). Falls back to a
minimal, best-effort platform implementation so the tool works with zero
third-party dependencies.

The public surface is :func:`send_to_trash`, which raises :class:`TrashError`
on failure so callers can report a clear message instead of failing silently.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


class TrashError(Exception):
    """Raised when a path could not be moved to the OS trash."""


def _via_send2trash(path: Path) -> bool:
    try:
        import send2trash
    except Exception:
        return False
    try:
        send2trash.send2trash(str(path))
    except Exception as exc:  # pragma: no cover - depends on env
        raise TrashError(f"send2trash failed for {path}: {exc}") from exc
    return True


def _windows_recycle(path: Path) -> None:  # pragma: no cover - Windows only
    """Move a path to the Windows Recycle Bin via the Shell API (ctypes)."""
    import ctypes
    from ctypes import wintypes

    FO_DELETE = 0x0003
    FOF_ALLOWUNDO = 0x0040
    FOF_NOCONFIRMATION = 0x0010
    FOF_SILENT = 0x0004

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    # Path must be absolute and double-null terminated.
    full = os.path.abspath(str(path))
    op = SHFILEOPSTRUCTW()
    op.wFunc = FO_DELETE
    op.pFrom = full + "\x00\x00"
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if rc != 0:
        raise TrashError(f"SHFileOperationW returned {rc} for {path}")


def _freedesktop_trash(path: Path) -> None:  # pragma: no cover - Linux only
    """Move a path into the user's XDG trash with a .trashinfo record."""
    import shutil
    from datetime import datetime
    from urllib.parse import quote

    xdg_data = os.environ.get(
        "XDG_DATA_HOME", os.path.expanduser("~/.local/share")
    )
    trash_dir = Path(xdg_data) / "Trash"
    files_dir = trash_dir / "files"
    info_dir = trash_dir / "info"
    files_dir.mkdir(parents=True, exist_ok=True)
    info_dir.mkdir(parents=True, exist_ok=True)

    base = path.name
    dest = files_dir / base
    counter = 1
    while dest.exists():
        dest = files_dir / f"{base}.{counter}"
        counter += 1

    info = info_dir / f"{dest.name}.trashinfo"
    info.write_text(
        "[Trash Info]\n"
        f"Path={quote(str(path.resolve()))}\n"
        f"DeletionDate={datetime.now().isoformat()}\n",
        encoding="utf-8",
    )
    shutil.move(str(path), str(dest))


def _macos_trash(path: Path) -> None:  # pragma: no cover - macOS only
    """Move a path to the macOS Trash via AppleScript (Finder)."""
    import subprocess

    script = (
        'tell application "Finder" to delete POSIX file '
        f'"{os.path.abspath(str(path))}"'
    )
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TrashError(result.stderr.strip() or "osascript failed")


def send_to_trash(path: str | os.PathLike[str]) -> None:
    """Move ``path`` to the OS trash. Raises :class:`TrashError` on failure.

    Resolution order:
        1. ``send2trash`` package (preferred, most robust).
        2. Built-in per-platform fallback.
    """
    p = Path(path)
    if not p.exists() and not p.is_symlink():
        raise TrashError(f"path does not exist: {p}")

    if _via_send2trash(p):
        return

    if sys.platform.startswith("win"):
        _windows_recycle(p)
    elif sys.platform == "darwin":
        _macos_trash(p)
    else:
        _freedesktop_trash(p)
