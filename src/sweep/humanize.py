"""Human-friendly formatting and parsing helpers (pure, no I/O)."""

from __future__ import annotations

import re

_SIZE_UNITS: tuple[tuple[str, int], ...] = (
    ("B", 1),
    ("KB", 1000),
    ("MB", 1000**2),
    ("GB", 1000**3),
    ("TB", 1000**4),
    ("PB", 1000**5),
)

# Accept both decimal (KB=1000) and binary (KiB=1024) size suffixes on input.
_PARSE_SIZE_UNITS: dict[str, int] = {
    "b": 1,
    "k": 1000, "kb": 1000, "kib": 1024,
    "m": 1000**2, "mb": 1000**2, "mib": 1024**2,
    "g": 1000**3, "gb": 1000**3, "gib": 1024**3,
    "t": 1000**4, "tb": 1000**4, "tib": 1024**4,
}

_DURATION_UNITS: dict[str, int] = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 60 * 60 * 24,
    "w": 60 * 60 * 24 * 7,
    "y": 60 * 60 * 24 * 365,
}


def human_size(num_bytes: int) -> str:
    """Format a byte count as a short decimal string, e.g. ``1.5 GB``.

    Uses SI (1000-based) units, matching how disk vendors and ``du -h --si``
    report sizes. Negative values are formatted with a leading minus.
    """
    if num_bytes < 0:
        return "-" + human_size(-num_bytes)
    if num_bytes < 1000:
        return f"{num_bytes} B"
    value = float(num_bytes)
    unit = "B"
    for name, factor in _SIZE_UNITS:
        if num_bytes < factor * 1000:
            value = num_bytes / factor
            unit = name
            break
    else:  # pragma: no cover - only for astronomically large inputs
        name, factor = _SIZE_UNITS[-1]
        value = num_bytes / factor
        unit = name
    if value >= 100:
        return f"{value:.0f} {unit}"
    if value >= 10:
        return f"{value:.1f} {unit}"
    return f"{value:.2f} {unit}"


def parse_size(text: str) -> int:
    """Parse a human size string like ``100MB`` or ``1.5 GiB`` into bytes.

    Raises:
        ValueError: if the string cannot be parsed.
    """
    s = text.strip().lower().replace(" ", "")
    if not s:
        raise ValueError("empty size string")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([a-z]*)", s)
    if not m:
        raise ValueError(f"invalid size: {text!r}")
    number, unit = m.group(1), m.group(2) or "b"
    if unit not in _PARSE_SIZE_UNITS:
        raise ValueError(f"unknown size unit in {text!r}: {unit!r}")
    return int(float(number) * _PARSE_SIZE_UNITS[unit])


def parse_duration(text: str) -> int:
    """Parse a duration like ``90d``, ``2w``, ``12h`` into seconds.

    A bare number is interpreted as days for convenience (``--older-than 90``).

    Raises:
        ValueError: if the string cannot be parsed.
    """
    s = text.strip().lower().replace(" ", "")
    if not s:
        raise ValueError("empty duration string")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([smhdwy]?)", s)
    if not m:
        raise ValueError(f"invalid duration: {text!r}")
    number, unit = m.group(1), m.group(2) or "d"
    return int(float(number) * _DURATION_UNITS[unit])


def human_age(seconds: float) -> str:
    """Format an age in seconds as a compact string like ``92d`` or ``3h``."""
    seconds = int(seconds)
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    days = seconds // 86400
    if days < 365:
        return f"{days}d"
    years = days // 365
    rem_days = days % 365
    return f"{years}y{rem_days}d" if rem_days else f"{years}y"
