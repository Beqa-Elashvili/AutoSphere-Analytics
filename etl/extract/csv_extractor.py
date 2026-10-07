"""Extract: read raw CSV files as text and validate their column contract."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from etl.sources import SOURCE_COLUMNS


class SchemaValidationError(Exception):
    """A source file is missing, empty or lacks required columns (pipeline must stop)."""

    def __init__(self, table: str, message: str):
        self.table = table
        super().__init__(f"{table}: {message}")


@dataclass
class ExtractResult:
    data: dict[str, pd.DataFrame]
    warnings: list[str] = field(default_factory=list)


def read_raw_csv(path: Path) -> pd.DataFrame:
    """Read every value as text, so invalid values survive until they can be inspected.

    keep_default_na=False stops pandas from silently turning strings like 'N/A'
    or 'NA' into NaN. Data-quality rules decide what counts as missing.
    """
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def validate_columns(table: str, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    expected = SOURCE_COLUMNS[table]
    actual = [c.strip().lower() for c in df.columns]
    df = df.set_axis(actual, axis=1)
    missing = [c for c in expected if c not in actual]
    if missing:
        raise SchemaValidationError(table, f"missing required column(s) {missing}")
    if df.empty:
        raise SchemaValidationError(table, "file contains no rows")
    warnings = []
    extra = [c for c in actual if c not in expected]
    if extra:
        warnings.append(f"{table}: ignoring unexpected column(s) {extra}")
    return df[expected], warnings


def extract_all(raw_dir: Path) -> ExtractResult:
    data, warnings = {}, []
    for table in SOURCE_COLUMNS:
        path = raw_dir / f"{table}.csv"
        if not path.exists():
            raise SchemaValidationError(table, f"source file not found at {path}")
        df, w = validate_columns(table, read_raw_csv(path))
        data[table] = df
        warnings.extend(w)
    return ExtractResult(data, warnings)
