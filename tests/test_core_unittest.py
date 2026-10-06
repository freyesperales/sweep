"""Stdlib-only unittest coverage of the core, for environments without pytest.

Run with:  python -m unittest tests.test_core_unittest
(or:        python -m unittest discover -s tests -p "test_*unittest.py")

The pytest suite is richer, but this module guarantees the core logic is
exercisable using only the standard library.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Make ``src`` importable when run directly without installation.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from sweep import core, trash  # noqa: E402
from sweep.humanize import human_size, parse_duration, parse_size  # noqa: E402


def _write(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)


class CoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "projects"
        _write(self.root / "web" / "package.json", 20)
        _write(self.root / "web" / "node_modules" / "a.js", 3000)
        _write(self.root / "api" / "pyproject.toml", 20)
        _write(self.root / "api" / ".venv" / "site.py", 1500)
        _write(self.root / "rustapp" / "Cargo.toml", 20)
        _write(self.root / "rustapp" / "target" / "app", 5000)
        _write(self.root / "plainbuild" / "build" / "x.bin", 9999)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_matches_and_markers(self) -> None:
        names = {f.path.name for f in core.scan(self.root).findings}
        self.assertIn("node_modules", names)
        self.assertIn(".venv", names)
        self.assertIn("target", names)
        # `build` without a manifest must not match.
        builds = [
            f for f in core.scan(self.root).findings
            if f.path.name == "build"
        ]
        self.assertEqual(builds, [])

    def test_sorted_by_size_desc(self) -> None:
        findings = core.scan(self.root).findings
        sizes = [f.size_bytes for f in findings]
        self.assertEqual(sizes, sorted(sizes, reverse=True))
        self.assertEqual(findings[0].size_bytes, 5000)

    def test_filters(self) -> None:
        now = time.time()
        findings = core.scan(self.root).findings
        big = core.filter_findings(findings, now=now, min_size=2000)
        names = {f.path.name for f in big}
        self.assertIn("target", names)
        self.assertNotIn(".venv", names)

    def test_stale_detection(self) -> None:
        old = time.time() - 200 * 86400
        target_dir = self.root / "rustapp" / "target"
        os.utime(target_dir / "app", (old, old))
        os.utime(target_dir, (old, old))
        now = time.time()
        f = next(x for x in core.scan(self.root).findings
                 if x.path.name == "target")
        self.assertTrue(f.is_stale(now))

    def test_delete_routes_to_trash(self) -> None:
        calls: list[str] = []
        original = trash.send_to_trash
        trash.send_to_trash = lambda p: calls.append(str(p))  # type: ignore
        try:
            f = core.scan(self.root).findings[0]
            core.delete_finding(f)
        finally:
            trash.send_to_trash = original  # type: ignore
        self.assertEqual(calls, [core.scan(self.root).findings[0].path
                                 .__str__()])

    def test_missing_root_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            core.scan(self.root / "nope")


class HumanizeTestCase(unittest.TestCase):
    def test_sizes(self) -> None:
        self.assertEqual(human_size(1000), "1.00 KB")
        self.assertEqual(human_size(47_300_000_000), "47.3 GB")

    def test_parse(self) -> None:
        self.assertEqual(parse_size("100MB"), 100_000_000)
        self.assertEqual(parse_duration("90d"), 90 * 86400)


if __name__ == "__main__":
    unittest.main()
