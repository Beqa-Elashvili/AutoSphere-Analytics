"""Reusable data-quality check framework.

A post-load check is declared as SQL that COUNTS VIOLATING ROWS. Builders such as
``unique()`` or ``foreign_key()`` generate that SQL, so a new rule is one line in
``etl/validation/rules.py``. The runner turns counts into PASS/FAIL results with a
severity, and those results become rows in ``audit.data_quality_report``.

Source-stage results are derived from the cleaning step itself (each rejection
reason and each automatic fix is a measured check), so cleaning rules and quality
measurement can never drift apart.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone

INFO, WARNING, CRITICAL = "INFO", "WARNING", "CRITICAL"
SEVERITIES = (INFO, WARNING, CRITICAL)


class DataQualityError(Exception):
    """Raised when at least one CRITICAL check fails. The pipeline must stop."""

    def __init__(self, failures: list["CheckResult"]):
        self.failures = failures
        names = ", ".join(f"{f.table_name}.{f.check_name}" for f in failures[:5])
        super().__init__(f"{len(failures)} critical data-quality check(s) failed: {names}")


@dataclass(frozen=True)
class Check:
    name: str
    table: str
    severity: str
    violation_sql: str             # must return a single integer: number of violating rows
    column: str | None = None
    description: str = ""
    max_failed_ratio: float = 0.0  # tolerated share of violating rows (completeness rules)


@dataclass
class CheckResult:
    check_name: str
    table_name: str
    stage: str
    status: str                    # PASS | FAIL
    severity: str
    failed_rows: int
    total_rows: int | None
    message: str
    column_name: str | None = None
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_critical_failure(self) -> bool:
        return self.status == "FAIL" and self.severity == CRITICAL

    def as_row(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------- builders
def condition(name: str, table: str, where: str, severity: str, column: str | None = None,
              description: str = "", max_failed_ratio: float = 0.0) -> Check:
    return Check(name, table, severity, f"SELECT count(*) FROM {table} WHERE {where}",
                 column, description, max_failed_ratio)


def unique(table: str, column: str, severity: str = CRITICAL) -> Check:
    sql = (f"SELECT COALESCE(SUM(n - 1), 0) FROM "
           f"(SELECT count(*) AS n FROM {table} GROUP BY {column} HAVING count(*) > 1) d")
    return Check(f"unique_{column}", table, severity, sql, column, f"{column} must be unique")


def not_null(table: str, column: str, severity: str = CRITICAL, max_failed_ratio: float = 0.0) -> Check:
    if max_failed_ratio:
        desc = f"{column} completeness (at most {max_failed_ratio:.0%} missing)"
        name = f"completeness_{column}"
    else:
        desc, name = f"{column} must not be NULL", f"not_null_{column}"
    return condition(name, table, f"{column} IS NULL", severity, column, desc, max_failed_ratio)


def foreign_key(table: str, column: str, parent: str, parent_column: str | None = None,
                severity: str = CRITICAL) -> Check:
    pc = parent_column or column
    sql = (f"SELECT count(*) FROM {table} c WHERE c.{column} IS NOT NULL AND NOT EXISTS "
           f"(SELECT 1 FROM {parent} p WHERE p.{pc} = c.{column})")
    return Check(f"fk_{column}", table, severity, sql, column, f"{column} must exist in {parent}.{pc}")


def allowed_values(table: str, column: str, values: set[str], severity: str = CRITICAL) -> Check:
    in_list = ", ".join(f"'{v}'" for v in sorted(values))
    return condition(f"allowed_values_{column}", table, f"{column} NOT IN ({in_list})", severity, column,
                     f"{column} must be one of {sorted(values)}")


def not_future(table: str, column: str, severity: str = CRITICAL) -> Check:
    return condition(f"not_future_{column}", table, f"{column} >= (%(as_of)s::date + 1)", severity, column,
                     f"{column} must not be after the extraction date")


def non_negative(table: str, column: str, severity: str = CRITICAL) -> Check:
    return condition(f"non_negative_{column}", table, f"{column} < 0", severity, column, f"{column} must be >= 0")


def positive(table: str, column: str, severity: str = CRITICAL) -> Check:
    return condition(f"positive_{column}", table, f"{column} <= 0", severity, column, f"{column} must be > 0")


def min_rows(table: str, minimum: int = 1) -> Check:
    return Check("row_count_minimum", table, CRITICAL,
                 f"SELECT CASE WHEN count(*) >= {minimum} THEN 0 ELSE 1 END FROM {table}",
                 None, f"table must contain at least {minimum} row(s)")


# ---------------------------------------------------------------------- runner
def run_checks(cursor, checks: list[Check], as_of: date, stage: str = "post_load") -> list[CheckResult]:
    """Execute SQL checks with a DB-API cursor (works inside an open transaction)."""
    totals: dict[str, int] = {}
    results = []
    for chk in checks:
        cursor.execute(chk.violation_sql, {"as_of": as_of})
        failed = int(cursor.fetchone()[0])
        if chk.table not in totals:
            cursor.execute(f"SELECT count(*) FROM {chk.table}")
            totals[chk.table] = int(cursor.fetchone()[0])
        total = totals[chk.table]
        ratio = failed / total if total else float(failed > 0)
        status = "PASS" if failed == 0 or ratio <= chk.max_failed_ratio else "FAIL"
        message = f"{chk.description}: {failed:,} of {total:,} rows ({ratio:.2%})"
        results.append(CheckResult(chk.name, chk.table, stage, status, chk.severity, failed, total,
                                   message, chk.column))
    return results


def critical_failures(results: list[CheckResult]) -> list[CheckResult]:
    return [r for r in results if r.is_critical_failure]


def raise_on_critical(results: list[CheckResult]) -> None:
    failures = critical_failures(results)
    if failures:
        raise DataQualityError(failures)
