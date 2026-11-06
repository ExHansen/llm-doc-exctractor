from datetime import date
from decimal import Decimal

import pytest

from docex.validation.normalize import (
    ParseError,
    is_valid_npwp,
    normalize_text,
    npwp_digits,
    parse_date,
    parse_number,
    parse_rate,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Rp 1.234.567,00", "1234567.00"),
        ("1.234.567", "1234567"),
        ("1,234,567", "1234567"),
        ("IDR 1,234,567.50", "1234567.50"),
        ("@15.000", "15000"),
        ("x2", "2"),
        ("2 x", "2"),
        ("12.5", "12.5"),
        ("1,5", "1.5"),
        ("-5,000", "-5000"),
        ("Rp. 25.000", "25000"),
        (1500, "1500"),
        (12.5, "12.5"),
        (Decimal("7.25"), "7.25"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_parse_number(raw, expected):
    assert parse_number(raw) == (Decimal(expected) if expected else None)


@pytest.mark.parametrize("raw", ["12a.000", "1.2.3,4,5", "abc", "1.23.456"])
def test_parse_number_rejects_garbage(raw):
    with pytest.raises(ParseError):
        parse_number(raw)


@pytest.mark.parametrize(
    "raw",
    ["05 November 2026", "05/11/2026", "2026-11-05", "5 Nov 2026", "5 nov 2026", "05-11-2026"],
)
def test_parse_date_variants(raw):
    assert parse_date(raw) == date(2026, 11, 5)


def test_parse_date_indonesian_month():
    assert parse_date("17 Agustus 2026") == date(2026, 8, 17)
    assert parse_date("3 Okt 2026") == date(2026, 10, 3)
    assert parse_date("1 Mei 2026") == date(2026, 5, 1)
    assert parse_date("24 Des 2025") == date(2025, 12, 24)


def test_parse_date_passthrough_and_blank():
    assert parse_date(date(2026, 1, 2)) == date(2026, 1, 2)
    assert parse_date(None) is None and parse_date("") is None


@pytest.mark.parametrize("raw", ["31/02/2026", "2026-13-01", "5 Foo 2026", "tomorrow"])
def test_parse_date_invalid(raw):
    with pytest.raises(ParseError):
        parse_date(raw)


def test_rates():
    assert parse_rate("11%") == Decimal("0.11")
    assert parse_rate("0.12") == Decimal("0.12")
    assert parse_rate(12) == Decimal("0.12")
    assert parse_rate("12 %") == Decimal("0.12")
    assert parse_rate(None) is None


def test_npwp():
    assert npwp_digits("01.234.567.8-901.000") == "012345678901000"
    assert npwp_digits("") is None and npwp_digits(None) is None
    assert is_valid_npwp("012345678901000") and is_valid_npwp("0123456789012345")
    assert not is_valid_npwp("01234567890100") and not is_valid_npwp(None)


def test_normalize_text():
    assert normalize_text("  PT.  Maju   Jaya, ") == "pt. maju jaya"
    assert normalize_text(None) == ""


@pytest.mark.parametrize(
    "raw,expected",
    [("0.005", "0.005"), ("0.500", "0.500"), ("0,250", "0.250"), ("0.008", "0.008")],
)
def test_leading_zero_group_is_decimal_not_thousands(raw, expected):
    assert parse_number(raw) == Decimal(expected)


def test_rate_with_trailing_zero():
    assert parse_rate("0.110") == Decimal("0.11")


@pytest.mark.parametrize(
    "raw,expected", [("1", "0.01"), ("1%", "0.01"), ("1.5", "0.015"), ("100%", "1"), ("0.5", "0.5")]
)
def test_rate_percent_heuristic(raw, expected):
    assert parse_rate(raw) == Decimal(expected)
