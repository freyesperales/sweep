"""Tests for the humanize formatting/parsing helpers."""

from __future__ import annotations

import pytest

from sweep.humanize import (
    human_age,
    human_size,
    parse_duration,
    parse_size,
)


@pytest.mark.parametrize(
    "n,expected",
    [
        (0, "0 B"),
        (512, "512 B"),
        (1000, "1.00 KB"),
        (1500, "1.50 KB"),
        (1_000_000, "1.00 MB"),
        (47_300_000_000, "47.3 GB"),
        (1_500_000_000, "1.50 GB"),
        (250_000_000_000, "250 GB"),
    ],
)
def test_human_size(n: int, expected: str) -> None:
    assert human_size(n) == expected


def test_human_size_negative() -> None:
    assert human_size(-1000) == "-1.00 KB"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("0", 0),
        ("100", 100),
        ("1KB", 1000),
        ("1kb", 1000),
        ("1KiB", 1024),
        ("100MB", 100_000_000),
        ("1.5GB", 1_500_000_000),
        ("2 GiB", 2 * 1024**3),
    ],
)
def test_parse_size(text: str, expected: int) -> None:
    assert parse_size(text) == expected


@pytest.mark.parametrize("bad", ["", "abc", "10xy", "GB"])
def test_parse_size_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_size(bad)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("90", 90 * 86400),       # bare number == days
        ("90d", 90 * 86400),
        ("2w", 2 * 7 * 86400),
        ("12h", 12 * 3600),
        ("30m", 30 * 60),
        ("45s", 45),
        ("1y", 365 * 86400),
    ],
)
def test_parse_duration(text: str, expected: int) -> None:
    assert parse_duration(text) == expected


@pytest.mark.parametrize("bad", ["", "abc", "10x"])
def test_parse_duration_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_duration(bad)


@pytest.mark.parametrize(
    "secs,expected",
    [
        (5, "5s"),
        (90, "1m"),
        (3700, "1h"),
        (90 * 86400, "90d"),
        (400 * 86400, "1y35d"),
        (365 * 86400, "1y"),
    ],
)
def test_human_age(secs: int, expected: str) -> None:
    assert human_age(secs) == expected
