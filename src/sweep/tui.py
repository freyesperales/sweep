"""Thin interactive TUI layer over the core scan results.

Kept deliberately small and dependency-free. On Windows we use ``msvcrt`` for
single-key input; on POSIX we use ``termios``/``tty`` raw mode. If neither is
available (e.g. a non-terminal), we fall back to a simple line-based prompt.

The TUI never deletes without an explicit confirmation step.
"""

from __future__ import annotations

import sys
import time
from typing import Sequence

from .core import Finding, delete_finding
from .humanize import human_age, human_size
from .trash import TrashError


def _read_key() -> str:
    """Read a single keypress and return a normalized token.

    Returns tokens like 'up', 'down', 'space', 'enter', 'q', 'd', 'a', or the
    literal character. Returns '' on EOF.
    """
    if sys.platform.startswith("win"):
        import msvcrt

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):  # special key prefix
            ch2 = msvcrt.getwch()
            return {"H": "up", "P": "down"}.get(ch2, "")
        return _normalize(ch)
    else:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":  # escape sequence
                seq = sys.stdin.read(2)
                return {"[A": "up", "[B": "down"}.get(seq, "")
            return _normalize(ch)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _normalize(ch: str) -> str:
    if ch in ("\r", "\n"):
        return "enter"
    if ch == " ":
        return "space"
    if ch in ("\x03",):  # Ctrl-C
        raise KeyboardInterrupt
    return ch.lower()


class _Palette:
    def __init__(self, enabled: bool) -> None:
        self.e = enabled

    def w(self, code: str, t: str) -> str:
        return f"\033[{code}m{t}\033[0m" if self.e else t


def _render(findings: Sequence[Finding], selected: set[int], cursor: int,
            now: float, p: _Palette) -> str:
    lines: list[str] = []
    total = sum(f.size_bytes for f in findings)
    sel_total = sum(findings[i].size_bytes for i in selected)
    lines.append(p.w("1", "sweep — reclaim dev disk"))
    lines.append(
        p.w("2", "[space] select  [a] all  [n] none  [d] delete→trash  "
            "[q] quit")
    )
    lines.append(
        p.w("36", f"{len(findings)} items, {human_size(total)} total")
        + "   "
        + p.w("32", f"selected: {len(selected)} ({human_size(sel_total)})")
    )
    lines.append("")
    if not findings:
        lines.append("  (nothing to reclaim)")
        return "\n".join(lines)

    size_w = max(9, max(len(human_size(f.size_bytes)) for f in findings))
    for i, f in enumerate(findings):
        marker = "x" if i in selected else " "
        pointer = ">" if i == cursor else " "
        size = human_size(f.size_bytes).rjust(size_w)
        age = human_age(f.age_seconds(now)).rjust(5)
        stale = f.is_stale(now)
        age_cell = p.w("33", age) if stale else age
        row = (
            f"{pointer} [{marker}] {p.w('36', size)}  {age_cell}  "
            f"{p.w('2', f.ecosystem)}  {f.path}"
        )
        if i == cursor:
            row = p.w("7", row)  # reverse video for the cursor line
        lines.append(row)
    return "\n".join(lines)


def _clear() -> None:
    sys.stdout.write("\033[2J\033[H")


def run_tui(findings: Sequence[Finding], *, now: float | None = None,
            color: bool = True) -> int:
    """Run the interactive selection UI. Returns a process exit code."""
    now = now if now is not None else time.time()
    p = _Palette(color)

    if not findings:
        print("No reclaimable artifacts found. Your disk is clean. 🎉")
        return 0

    # Fall back to a non-raw prompt if stdin isn't an interactive terminal.
    if not sys.stdin.isatty():
        return _fallback_prompt(findings, now, p)

    selected: set[int] = set()
    cursor = 0
    try:
        while True:
            _clear()
            sys.stdout.write(_render(findings, selected, cursor, now, p))
            sys.stdout.write("\n")
            sys.stdout.flush()
            key = _read_key()
            if key in ("q", ""):
                print("\nNothing deleted. Bye.")
                return 0
            if key == "up":
                cursor = (cursor - 1) % len(findings)
            elif key == "down":
                cursor = (cursor + 1) % len(findings)
            elif key == "space":
                selected.symmetric_difference_update({cursor})
            elif key == "a":
                selected = set(range(len(findings)))
            elif key == "n":
                selected.clear()
            elif key == "d":
                if not selected:
                    continue
                if _confirm_delete(findings, selected, now, p):
                    return _do_delete(findings, selected, p)
    except KeyboardInterrupt:
        print("\nAborted. Nothing deleted.")
        return 130


def _confirm_delete(findings: Sequence[Finding], selected: set[int],
                    now: float, p: _Palette) -> bool:
    _clear()
    total = sum(findings[i].size_bytes for i in selected)
    print(p.w("1", f"About to move {len(selected)} item(s) "
                   f"({human_size(total)}) to the trash:"))
    print()
    for i in sorted(selected, key=lambda j: findings[j].size_bytes,
                    reverse=True):
        f = findings[i]
        print(f"  {human_size(f.size_bytes):>10}  {f.path}")
    print()
    print(p.w("33", "These go to the OS trash and can be restored."))
    sys.stdout.write("Proceed? [y/N] ")
    sys.stdout.flush()
    try:
        resp = input().strip().lower()
    except EOFError:
        return False
    return resp in ("y", "yes")


def _do_delete(findings: Sequence[Finding], selected: set[int],
               p: _Palette) -> int:
    reclaimed = 0
    failures = 0
    for i in sorted(selected):
        f = findings[i]
        try:
            delete_finding(f)
            reclaimed += f.size_bytes
            print(p.w("32", f"trashed {f.path}"))
        except TrashError as exc:
            failures += 1
            print(p.w("31", f"failed: {f.path}: {exc}"))
    print()
    print(p.w("1", f"Reclaimed {human_size(reclaimed)}."))
    return 1 if failures else 0


def _fallback_prompt(findings: Sequence[Finding], now: float,
                     p: _Palette) -> int:
    """Line-based selection when no raw terminal is available."""
    size_w = max(9, max(len(human_size(f.size_bytes)) for f in findings))
    for i, f in enumerate(findings):
        stale = " (stale)" if f.is_stale(now) else ""
        print(f"[{i:>3}] {human_size(f.size_bytes):>{size_w}}  "
              f"{human_age(f.age_seconds(now)):>5}  {f.ecosystem:<9}  "
              f"{f.path}{stale}")
    print()
    sys.stdout.write(
        "Enter indices to trash (comma/space separated), 'all', or blank to "
        "cancel: "
    )
    sys.stdout.flush()
    try:
        raw = input().strip()
    except EOFError:
        print("No input; nothing deleted.")
        return 0
    if not raw:
        print("Nothing deleted.")
        return 0
    if raw.lower() == "all":
        chosen = set(range(len(findings)))
    else:
        chosen = set()
        for tok in raw.replace(",", " ").split():
            try:
                idx = int(tok)
            except ValueError:
                continue
            if 0 <= idx < len(findings):
                chosen.add(idx)
    if not chosen:
        print("No valid indices; nothing deleted.")
        return 0
    if not _confirm_delete(findings, chosen, now, p):
        print("Cancelled.")
        return 0
    return _do_delete(findings, chosen, p)
