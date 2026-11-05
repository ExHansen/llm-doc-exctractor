"""Parse the number, date, rate and NPWP formats found on Indonesian documents."""

from __future__ import annotations

import re
import string
from datetime import date
from decimal import Decimal, InvalidOperation


class ParseError(ValueError):
    """A value is present but cannot be read as the expected type."""


_CURRENCY = re.compile(r"(?i)\b(rp|idr)\b\.?|rp\.?|[@x×\s]")
_GROUPED = re.compile(r"^\d{1,3}(\d{3})*$")

MONTHS = {
    "januari": 1, "january": 1, "jan": 1,
    "februari": 2, "february": 2, "feb": 2,
    "maret": 3, "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mei": 5, "may": 5,
    "juni": 6, "june": 6, "jun": 6,
    "juli": 7, "july": 7, "jul": 7,
    "agustus": 8, "august": 8, "agu": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "october": 10, "okt": 10, "oct": 10,
    "november": 11, "nov": 11,
    "desember": 12, "december": 12, "des": 12, "dec": 12,
}  # fmt: skip

_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_DMY = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$")
_TEXTUAL = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})$")


def _is_thousands(parts: list[str]) -> bool:
    """`1.234.567` groups; a leading `0` group (`0.005`) is a decimal, not thousands."""
    return (
        len(parts) > 1
        and parts[0] != "0"
        and 1 <= len(parts[0]) <= 3
        and all(len(p) == 3 for p in parts[1:])
    )


def parse_number(value: str | int | float | Decimal | None) -> Decimal | None:
    """Read a number written as `Rp 1.234.567,00`, `1,234,567.50`, `@15.000`, `x2`, ..."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ParseError(f"not a number: {value!r}")
    if isinstance(value, int | float):
        return Decimal(str(value))
    text = value.strip()
    if not text:
        return None
    negative = text.startswith("-")
    body = _CURRENCY.sub("", text.lstrip("-")).strip()
    if not body:
        raise ParseError(f"not a number: {value!r}")
    if "," in body and "." in body:
        decimal_sep = "," if body.rfind(",") > body.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        integer, _, fraction = body.rpartition(decimal_sep)
        groups = integer.split(thousands_sep)
        if len(groups) > 1 and not _is_thousands(groups):
            raise ParseError(f"not a number: {value!r}")
        normalized = "".join(groups) + "." + fraction
    elif "." in body or "," in body:
        sep = "." if "." in body else ","
        parts = body.split(sep)
        if _is_thousands(parts):
            normalized = "".join(parts)
        elif len(parts) == 2:
            normalized = parts[0] + "." + parts[1]
        else:
            raise ParseError(f"not a number: {value!r}")
    else:
        normalized = body
    if not re.fullmatch(r"\d+(\.\d+)?", normalized):
        raise ParseError(f"not a number: {value!r}")
    try:
        result = Decimal(normalized)
    except InvalidOperation as exc:  # pragma: no cover - guarded by the regex above
        raise ParseError(f"not a number: {value!r}") from exc
    return -result if negative else result


def parse_rate(value: str | int | float | Decimal | None) -> Decimal | None:
    """Read a tax rate: `11%`, `0.11` and `11` all mean 0.11."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.replace("%", "").strip()
        if not text:
            return None
        number = parse_number(text)
    else:
        number = parse_number(value)
    if number is None:
        return None
    if number > 1:
        number = number / Decimal(100)
    return number.normalize() if number == number.to_integral() else number


def _make_date(year: int, month: int, day: int, raw: object) -> date:
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ParseError(f"not a valid date: {raw!r}") from exc


def parse_date(value: str | date | None) -> date | None:
    """Read `2026-11-05`, `05/11/2026` (day first), `5 Nov 2026`, `17 Agustus 2026`, ..."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = value.strip()
    if not text:
        return None
    if m := _ISO.match(text):
        return _make_date(int(m[1]), int(m[2]), int(m[3]), value)
    if m := _DMY.match(text):
        return _make_date(int(m[3]), int(m[2]), int(m[1]), value)
    if m := _TEXTUAL.match(text):
        month = MONTHS.get(m[2].lower())
        if month is None:
            raise ParseError(f"unknown month in date: {value!r}")
        return _make_date(int(m[3]), month, int(m[1]), value)
    raise ParseError(f"not a date: {value!r}")


def npwp_digits(value: str | None) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits or None


def is_valid_npwp(digits: str | None) -> bool:
    """NPWP is 15 digits (old format) or 16 digits (NIK-based, since 2024)."""
    return digits is not None and digits.isdigit() and len(digits) in (15, 16)


_EDGE_PUNCT = string.punctuation + " "


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    collapsed = " ".join(str(value).casefold().split())
    return collapsed.strip(_EDGE_PUNCT)
