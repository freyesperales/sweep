"""sweep — reclaim your dev disk.

Find and delete node_modules, .venv, target, build caches across every
project. Cross-ecosystem, size-sorted, age-aware, and reversible (deletes go
to the OS trash).

The public, importable API lives in :mod:`sweep.core`.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .core import (  # noqa: E402
    Finding,
    ScanStats,
    delete_finding,
    filter_findings,
    scan,
)
from .rules import RULES, Rule, ecosystems  # noqa: E402

__all__ = [
    "__version__",
    "Finding",
    "ScanStats",
    "Rule",
    "RULES",
    "scan",
    "filter_findings",
    "delete_finding",
    "ecosystems",
]
