"""Command-line interface for sweep."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Sequence, TextIO

from . import __version__
from .core import (
    Finding,
    ScanStats,
    STALE_THRESHOLD_SECONDS,
    delete_finding,
    filter_findings,
    scan,
)
from .humanize import human_age, human_size, parse_duration, parse_size
from .rules import ecosystems as all_ecosystems
from .trash import TrashError

# ANSI helpers (disabled when output is not a TTY or NO_COLOR is set).
import os as _os


def _use_color(stream: TextIO) -> bool:
    if _os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


class _C:
    def __init__(self, enabled: bool) -> None:
        self.e = enabled

    def _w(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.e else text

    def dim(self, t: str) -> str:
        return self._w("2", t)

    def bold(self, t: str) -> str:
        return self._w("1", t)

    def red(self, t: str) -> str:
        return self._w("31", t)

    def green(self, t: str) -> str:
        return self._w("32", t)

    def yellow(self, t: str) -> str:
        return self._w("33", t)

    def cyan(self, t: str) -> str:
        return self._w("36", t)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sweep",
        description=(
            "Reclaim dev disk: find and delete node_modules, .venv, target, "
            "build caches across every project. Deletes go to the OS trash "
            "(reversible)."
        ),
        epilog="Development Experiment 061 of dev-experiments-365.",
    )
    p.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Root directory to scan (default: current directory).",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"sweep {__version__}",
    )
    p.add_argument(
        "--min-size",
        metavar="SIZE",
        default="0",
        help="Only show artifacts at least this large, e.g. 100MB, 1.5GB.",
    )
    p.add_argument(
        "--older-than",
        metavar="AGE",
        default=None,
        help="Only show artifacts not modified in at least AGE, e.g. 90d, 2w.",
    )
    p.add_argument(
        "--ecosystem",
        metavar="NAME",
        action="append",
        default=None,
        help=(
            "Limit to one or more ecosystems (repeatable). "
            f"Available: {', '.join(all_ecosystems())}."
        ),
    )
    p.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of threads used to size directories (default: 8).",
    )
    mode = p.add_argument_group("modes")
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without deleting anything.",
    )
    mode.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Delete all matching artifacts to trash without prompting.",
    )
    mode.add_argument(
        "--json",
        action="store_true",
        help="Emit findings as JSON to stdout (implies non-interactive).",
    )
    mode.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Force the interactive TUI (default when stdout is a terminal "
        "and no other mode flag is given).",
    )
    return p


def _finding_to_dict(f: Finding, now: float) -> dict[str, Any]:
    return {
        "path": str(f.path),
        "ecosystem": f.ecosystem,
        "rule": f.rule.dir_name,
        "description": f.rule.description,
        "size_bytes": f.size_bytes,
        "size_human": human_size(f.size_bytes),
        "file_count": f.file_count,
        "age_seconds": int(f.age_seconds(now)),
        "age_human": human_age(f.age_seconds(now)),
        "stale": f.is_stale(now),
        "mtime": f.mtime,
        "error": f.error,
    }


def _print_table(findings: Sequence[Finding], now: float, c: _C,
                 stream: TextIO) -> None:
    if not findings:
        print("No reclaimable artifacts matched the filters.", file=stream)
        return
    size_w = max(9, max(len(human_size(f.size_bytes)) for f in findings))
    eco_w = max(9, max(len(f.ecosystem) for f in findings))
    header = (
        f"{'SIZE':>{size_w}}  {'AGE':>5}  {'ECOSYSTEM':<{eco_w}}  PATH"
    )
    print(c.bold(header), file=stream)
    print(c.dim("-" * len(header)), file=stream)
    for f in findings:
        size = human_size(f.size_bytes).rjust(size_w)
        age = human_age(f.age_seconds(now)).rjust(5)
        eco = f.ecosystem.ljust(eco_w)
        stale = f.is_stale(now)
        age_str = c.yellow(age) if stale else age
        line = f"{c.cyan(size)}  {age_str}  {c.dim(eco)}  {f.path}"
        if f.error:
            line += c.red(f"  [!] {f.error}")
        print(line, file=stream)


def _summary_line(findings: Sequence[Finding], c: _C) -> str:
    total = sum(f.size_bytes for f in findings)
    return c.bold(
        f"{len(findings)} item(s), {human_size(total)} reclaimable."
    )


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    out = sys.stdout
    err = sys.stderr
    c = _C(_use_color(out))

    root = Path(args.path)

    # Parse filters early so bad input fails fast with a clear message.
    try:
        min_size = parse_size(args.min_size)
    except ValueError as exc:
        print(c.red(f"error: --min-size: {exc}"), file=err)
        return 2
    older_than_seconds: int | None = None
    if args.older_than is not None:
        try:
            older_than_seconds = parse_duration(args.older_than)
        except ValueError as exc:
            print(c.red(f"error: --older-than: {exc}"), file=err)
            return 2

    ecosystems: frozenset[str] | None = None
    if args.ecosystem:
        requested = frozenset(args.ecosystem)
        known = frozenset(all_ecosystems())
        unknown = requested - known
        if unknown:
            print(
                c.red(
                    "error: unknown ecosystem(s): "
                    f"{', '.join(sorted(unknown))}. "
                    f"Known: {', '.join(sorted(known))}."
                ),
                file=err,
            )
            return 2
        ecosystems = requested

    try:
        if not args.json:
            print(c.dim(f"Scanning {root.resolve()} ..."), file=err)
        stats: ScanStats = scan(root, workers=args.workers)
    except FileNotFoundError as exc:
        print(c.red(f"error: {exc}"), file=err)
        return 2
    except NotADirectoryError as exc:
        print(c.red(f"error: {exc}"), file=err)
        return 2

    now = time.time()
    findings = filter_findings(
        stats.findings,
        now=now,
        min_size=min_size,
        older_than_seconds=older_than_seconds,
        ecosystems=ecosystems,
    )

    # JSON mode: emit and exit (never deletes).
    if args.json:
        payload = {
            "root": str(root.resolve()),
            "scanned_dirs": stats.scanned_dirs,
            "permission_errors": stats.permission_errors,
            "total_reclaimable_bytes": sum(f.size_bytes for f in findings),
            "count": len(findings),
            "findings": [_finding_to_dict(f, now) for f in findings],
        }
        json.dump(payload, out, indent=2)
        out.write("\n")
        return 0

    # Decide mode.
    interactive = args.interactive or (
        not args.dry_run
        and not args.yes
        and out.isatty()
        and err.isatty()
    )

    if interactive:
        from .tui import run_tui

        return run_tui(findings, now=now, color=c.e)

    # Non-interactive text report.
    _print_table(findings, now, c, out)
    print(file=out)
    print(_summary_line(findings, c), file=out)

    if stats.permission_errors:
        print(
            c.dim(
                f"({len(stats.permission_errors)} director"
                f"{'y' if len(stats.permission_errors) == 1 else 'ies'} "
                "skipped due to permission errors)"
            ),
            file=err,
        )

    if args.dry_run or not findings:
        if args.dry_run:
            print(c.dim("Dry run: nothing was deleted."), file=out)
        return 0

    if not args.yes:
        # Non-interactive but not --yes and not --dry-run: require confirmation.
        print(
            c.yellow(
                "\nRefusing to delete without confirmation. "
                "Re-run with --yes to delete to trash, or --dry-run to preview."
            ),
            file=err,
        )
        return 0

    # --yes path: delete everything shown, to trash.
    return _delete_all(findings, c, out, err)


def _delete_all(findings: Sequence[Finding], c: _C, out: TextIO,
                err: TextIO) -> int:
    deleted = 0
    reclaimed = 0
    failures = 0
    for f in findings:
        try:
            delete_finding(f)
            deleted += 1
            reclaimed += f.size_bytes
            print(c.green(f"trashed {f.path}  ({human_size(f.size_bytes)})"),
                  file=out)
        except TrashError as exc:
            failures += 1
            print(c.red(f"failed to trash {f.path}: {exc}"), file=err)
    print(file=out)
    print(
        c.bold(f"Reclaimed {human_size(reclaimed)} across {deleted} item(s)."),
        file=out,
    )
    if failures:
        print(c.red(f"{failures} item(s) could not be trashed."), file=err)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(argv)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
