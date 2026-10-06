"""Core scan / match / size / age logic for sweep.

This module is pure and importable: it performs no interactive I/O, no printing,
and (apart from reading the filesystem) no destructive actions. The one
side-effecting helper, :func:`delete_finding`, is explicit and routes through
the trash layer. This separation keeps the logic fully unit-testable.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from . import trash
from .rules import RULES, Rule

# Default: directories older (unmodified) than this are flagged "stale".
STALE_THRESHOLD_SECONDS: int = 90 * 24 * 60 * 60


@dataclass(slots=True)
class Finding:
    """A matched reclaimable directory with computed metadata."""

    path: Path
    rule: Rule
    size_bytes: int
    file_count: int
    mtime: float  # last-modified epoch seconds (newest entry within the dir)
    error: str | None = None  # non-fatal issue encountered while sizing

    @property
    def ecosystem(self) -> str:
        return self.rule.ecosystem

    def age_seconds(self, now: float) -> float:
        return max(0.0, now - self.mtime)

    def is_stale(self, now: float,
                 threshold: int = STALE_THRESHOLD_SECONDS) -> bool:
        return self.age_seconds(now) >= threshold


@dataclass(slots=True)
class ScanStats:
    """Summary of a scan run."""

    findings: list[Finding] = field(default_factory=list)
    scanned_dirs: int = 0
    permission_errors: list[str] = field(default_factory=list)

    @property
    def total_bytes(self) -> int:
        return sum(f.size_bytes for f in self.findings)


def _matches(dir_name: str, parent: Path) -> Rule | None:
    """Return the first rule matching ``dir_name`` at ``parent``, else None.

    A rule with ``marker_files`` only matches when at least one marker exists
    as a sibling of the candidate directory (i.e. inside ``parent``). Markers
    may contain a single ``*`` glob (e.g. ``*.csproj``).
    """
    for rule in RULES:
        if rule.dir_name != dir_name:
            continue
        if not rule.marker_files:
            return rule
        for marker in rule.marker_files:
            if "*" in marker:
                try:
                    if any(parent.glob(marker)):
                        return rule
                except OSError:
                    continue
            elif (parent / marker).exists():
                return rule
    return None


def iter_candidates(root: Path) -> Iterable[tuple[Path, Rule]]:
    """Walk ``root`` and yield ``(path, rule)`` for each reclaimable dir.

    Once a reclaimable directory is matched, we do **not** descend into it
    (a nested ``node_modules`` inside another ``node_modules`` is already
    accounted for by its parent's size). Symlinked directories are never
    followed, preventing cycles and double-counting.
    """
    root = root.resolve()
    permission_errors: list[str] = []

    def _walk(current: Path) -> Iterable[tuple[Path, Rule]]:
        try:
            entries = list(os.scandir(current))
        except PermissionError:
            permission_errors.append(str(current))
            return
        except (FileNotFoundError, NotADirectoryError, OSError):
            return
        subdirs: list[Path] = []
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if not entry.is_dir():
                    continue
            except OSError:
                continue
            child = Path(entry.path)
            rule = _matches(entry.name, current)
            if rule is not None:
                yield child, rule
                # Do not descend into a matched reclaimable directory.
                continue
            subdirs.append(child)
        for sub in subdirs:
            yield from _walk(sub)

    yield from _walk(root)
    # Note: permission errors are discarded here. Callers that need to report
    # inaccessible directories should use `scan`, which collects them.
    del permission_errors


def directory_size(path: Path) -> tuple[int, int, float, str | None]:
    """Compute (total_bytes, file_count, newest_mtime, error) for a tree.

    Does not follow symlinks. Uses ``stat`` sizes on-disk apparent bytes.
    Permission or transient errors are recorded in the returned ``error``
    string rather than raised, so a single bad file never aborts the scan.
    """
    total = 0
    count = 0
    newest = 0.0
    error: str | None = None

    try:
        root_stat = path.lstat()
        newest = root_stat.st_mtime
    except OSError as exc:
        return 0, 0, 0.0, f"stat failed: {exc}"

    stack: list[str] = [str(path)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            # Count the link itself, do not follow it.
                            st = entry.stat(follow_symlinks=False)
                            total += st.st_size
                            count += 1
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                            continue
                        st = entry.stat(follow_symlinks=False)
                        total += st.st_size
                        count += 1
                        if st.st_mtime > newest:
                            newest = st.st_mtime
                    except OSError as exc:
                        error = f"partial: {exc}"
        except PermissionError as exc:
            error = f"permission denied: {exc}"
        except OSError as exc:
            error = f"partial: {exc}"

    return total, count, newest, error


def scan(
    root: str | os.PathLike[str],
    *,
    workers: int = 8,
    progress: Callable[[Finding], None] | None = None,
) -> ScanStats:
    """Scan ``root`` for reclaimable directories and size them concurrently.

    Args:
        root: Directory to scan.
        workers: Max threads used to compute directory sizes in parallel.
            Sizing is I/O bound, so threads give a real speedup.
        progress: Optional callback invoked with each completed Finding.

    Returns:
        A :class:`ScanStats` with findings sorted by size descending.

    Raises:
        FileNotFoundError: if ``root`` does not exist.
        NotADirectoryError: if ``root`` is not a directory.
    """
    root_path = Path(root)
    if not root_path.exists():
        raise FileNotFoundError(f"scan root does not exist: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"scan root is not a directory: {root_path}")

    stats = ScanStats()
    permission_errors: list[str] = []

    # Re-implement the walk here so we can capture permission errors (the
    # generator above cannot surface them through its closure).
    candidates: list[tuple[Path, Rule]] = []
    resolved_root = root_path.resolve()

    def _walk(current: Path) -> None:
        try:
            entries = list(os.scandir(current))
        except PermissionError:
            permission_errors.append(str(current))
            return
        except (FileNotFoundError, NotADirectoryError, OSError):
            return
        subdirs: list[Path] = []
        for entry in entries:
            try:
                if entry.is_symlink() or not entry.is_dir():
                    continue
            except OSError:
                continue
            child = Path(entry.path)
            rule = _matches(entry.name, current)
            if rule is not None:
                candidates.append((child, rule))
                continue
            subdirs.append(child)
        stats.scanned_dirs += 1
        for sub in subdirs:
            _walk(sub)

    _walk(resolved_root)
    stats.permission_errors = permission_errors

    if not candidates:
        return stats

    def _size(item: tuple[Path, Rule]) -> Finding:
        path, rule = item
        total, count, mtime, error = directory_size(path)
        return Finding(
            path=path,
            rule=rule,
            size_bytes=total,
            file_count=count,
            mtime=mtime,
            error=error,
        )

    workers = max(1, min(workers, len(candidates)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_size, item) for item in candidates]
        for fut in as_completed(futures):
            finding = fut.result()
            stats.findings.append(finding)
            if progress is not None:
                progress(finding)

    stats.findings.sort(key=lambda f: f.size_bytes, reverse=True)
    return stats


def filter_findings(
    findings: Iterable[Finding],
    *,
    now: float,
    min_size: int = 0,
    older_than_seconds: int | None = None,
    ecosystems: frozenset[str] | None = None,
) -> list[Finding]:
    """Return findings passing all of the given filters (AND semantics)."""
    result: list[Finding] = []
    for f in findings:
        if f.size_bytes < min_size:
            continue
        if older_than_seconds is not None and f.age_seconds(now) < older_than_seconds:
            continue
        if ecosystems is not None and f.ecosystem not in ecosystems:
            continue
        result.append(f)
    return result


def delete_finding(finding: Finding) -> None:
    """Move a finding's directory to the OS trash (reversible).

    Raises:
        trash.TrashError: if the delete could not be performed.
    """
    trash.send_to_trash(finding.path)
