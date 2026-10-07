"""Reusable, vectorized normalization functions for raw text columns.

Each parser returns NA for values it cannot interpret. The caller decides
whether that means "reject the row" or "set the attribute to NULL".
"""
from __future__ import annotations

import pandas as pd

from etl.transform.mappings import (
    ALLOWED, CANONICAL_CITIES, CITY_SYNONYMS, FALSE_VALUES, SYNONYMS, TRUE_VALUES, UNKNOWN_CITY,
)

# Source systems use day-first dates. ISO formats are tried first.
DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%b-%Y")
DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M",
    "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
) + DATE_FORMATS


def blank_to_na(s: pd.Series) -> pd.Series:
    s = s.astype("string").str.strip()
    return s.mask(s == "")


def clean_text(s: pd.Series) -> pd.Series:
    """Trim and collapse internal whitespace; empty -> NA."""
    return blank_to_na(s).str.replace(r"\s+", " ", regex=True)


def fix_shouting(s: pd.Series) -> pd.Series:
    """Title-case values written entirely in capitals or lowercase (names)."""
    s = clean_text(s)
    bad_case = (s.str.isupper() | s.str.islower()).fillna(False)
    return s.mask(bad_case, s.str.title())


def normalize_id(s: pd.Series) -> pd.Series:
    """Business keys: uppercase, no whitespace ('  cus00012 ' -> 'CUS00012')."""
    return blank_to_na(s).str.upper().str.replace(r"\s+", "", regex=True)


def parse_datetime(s: pd.Series, formats: tuple[str, ...] = DATETIME_FORMATS) -> pd.Series:
    """Try each explicit format in turn (never guess); unparseable -> NaT."""
    s = blank_to_na(s)
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    for fmt in formats:
        todo = out.isna() & s.notna()
        if not todo.any():
            break
        out.loc[todo] = pd.to_datetime(s[todo], format=fmt, errors="coerce")
    return out


def parse_date(s: pd.Series) -> pd.Series:
    return parse_datetime(s, DATE_FORMATS)


def parse_decimal(s: pd.Series) -> pd.Series:
    """'245.00', ' 245,00 ', '1,245.00' -> float; 'N/A' -> NA."""
    s = blank_to_na(s)
    has_dot = s.str.contains(".", regex=False).fillna(False)
    s = s.mask(has_dot, s.str.replace(",", "", regex=False))        # thousands separator
    s = s.mask(~has_dot, s.str.replace(",", ".", regex=False))      # decimal comma
    return pd.to_numeric(s, errors="coerce").astype("Float64")


def parse_int(s: pd.Series) -> pd.Series:
    num = parse_decimal(s)
    return num.where((num == num.round()).fillna(False)).astype("Int64")


def parse_bool(s: pd.Series) -> pd.Series:
    key = blank_to_na(s).str.lower()
    return key.map(lambda v: True if v in TRUE_VALUES else False if v in FALSE_VALUES else pd.NA).astype("boolean")


def normalize_category(s: pd.Series, domain: str) -> tuple[pd.Series, pd.Series]:
    """Map variants to canonical values for a domain.

    Returns (normalized values, invalid mask). Invalid = present but unmappable.
    """
    raw = blank_to_na(s)
    key = raw.str.lower().str.replace(r"[\s\-]+", "_", regex=True)
    key = key.replace(SYNONYMS.get(domain, {}))
    valid = key.isin(ALLOWED[domain]).fillna(False)
    return key.where(valid), raw.notna() & ~valid


def normalize_city(s: pd.Series) -> pd.Series:
    """Canonical city name. Unknown spellings are title-cased; blanks become 'Unknown'."""
    raw = clean_text(s)
    mapped = raw.str.lower().map(CITY_SYNONYMS)
    out = mapped.fillna(raw.str.title())
    return out.fillna(UNKNOWN_CITY).astype("string")


def is_canonical_city(s: pd.Series) -> pd.Series:
    return s.isin(CANONICAL_CITIES | {UNKNOWN_CITY})


def changed_mask(before: pd.Series, after: pd.Series) -> pd.Series:
    """Rows where a present raw value was altered by normalization (for fix statistics)."""
    b = before.astype("string")
    a = after.astype("string")
    present = b.str.strip() != ""
    return (present & a.notna() & (b != a)).fillna(False).astype(bool)
