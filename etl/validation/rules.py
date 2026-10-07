"""The data-quality rule catalog.

Severity policy:
  CRITICAL -> would make reported numbers wrong (duplicate keys, orphan transactions,
              negative money, future transactions). The pipeline stops / rolls back.
  WARNING  -> data is usable but degraded (master-data references mapped to
              'Unknown', non-canonical cities, low completeness, high rejection rate).
  INFO     -> measurements kept for trend monitoring (automatic fixes, profiling).
"""
from __future__ import annotations

from etl.sources import BUSINESS_KEYS
from etl.transform.cleaners import CleanResult
from etl.transform.mappings import ALLOWED, CANONICAL_CITIES, UNKNOWN_CITY
from etl.validation.checks import (
    CRITICAL, INFO, WARNING, Check, CheckResult, allowed_values, condition, foreign_key, min_rows,
    non_negative, not_future, not_null, positive, unique,
)

# Share of INVALID rows (rejections other than harmless duplicates) per source table.
REJECTION_RATE_WARNING = 0.02
REJECTION_RATE_CRITICAL = 0.10
DUPLICATE_REASONS = {"exact_duplicate", "duplicate_business_key", "duplicate_vin"}

S = "staging."


def _required(table: str, *columns: str) -> list[Check]:
    return [not_null(S + table, c) for c in columns]


def post_load_checks() -> list[Check]:
    checks: list[Check] = []

    # -- completeness of every table + primary-key uniqueness -------------------------
    for table, key in BUSINESS_KEYS.items():
        checks += [min_rows(S + table), unique(S + table, key), not_null(S + table, key)]

    # -- required attributes ------------------------------------------------------------
    checks += _required("sales", "invoice_number", "sale_datetime", "customer_id", "product_id",
                        "branch_id", "employee_id", "quantity", "unit_price", "unit_cost")
    checks += _required("service_orders", "vehicle_id", "customer_id", "branch_id", "employee_id", "opened_at")
    checks += _required("payments", "source_reference", "customer_id", "payment_datetime", "amount")
    checks += _required("customer_feedback", "customer_id", "branch_id", "feedback_date", "feedback_text")

    # -- referential integrity: transactions (CRITICAL) ---------------------------------
    checks += [
        foreign_key(S + "sales", "customer_id", S + "customers"),
        foreign_key(S + "sales", "product_id", S + "products"),
        foreign_key(S + "sales", "branch_id", S + "branches"),
        foreign_key(S + "sales", "employee_id", S + "employees"),
        foreign_key(S + "service_orders", "vehicle_id", S + "vehicles"),
        foreign_key(S + "service_orders", "customer_id", S + "customers"),
        foreign_key(S + "service_orders", "branch_id", S + "branches"),
        foreign_key(S + "service_orders", "employee_id", S + "employees"),
        foreign_key(S + "service_items", "service_order_id", S + "service_orders"),
        foreign_key(S + "service_items", "product_id", S + "products"),
        foreign_key(S + "payments", "customer_id", S + "customers"),
        foreign_key(S + "customer_feedback", "customer_id", S + "customers"),
        foreign_key(S + "customer_feedback", "branch_id", S + "branches"),
        foreign_key(S + "customer_feedback", "service_order_id", S + "service_orders"),
        condition("fk_source_reference", S + "payments",
                  "(source_type = 'sale' AND NOT EXISTS (SELECT 1 FROM staging.sales s "
                  "WHERE s.invoice_number = staging.payments.source_reference)) OR "
                  "(source_type = 'service' AND NOT EXISTS (SELECT 1 FROM staging.service_orders o "
                  "WHERE o.service_order_id = staging.payments.source_reference))",
                  CRITICAL, "source_reference", "payment must reference an existing invoice / service order"),
    ]

    # -- referential integrity: master data (WARNING: kept, mapped to Unknown in dw) -----
    checks += [
        foreign_key(S + "products", "category_id", S + "product_categories", severity=WARNING),
        foreign_key(S + "employees", "branch_id", S + "branches", severity=WARNING),
        foreign_key(S + "vehicles", "customer_id", S + "customers", severity=WARNING),
    ]

    # -- allowed categorical values ------------------------------------------------------
    checks += [
        allowed_values(S + "sales", "sales_channel", ALLOWED["sales_channel"]),
        allowed_values(S + "sales", "order_status", ALLOWED["sales_order_status"]),
        allowed_values(S + "service_orders", "service_type", ALLOWED["service_type"]),
        allowed_values(S + "payments", "payment_status", ALLOWED["payment_status"]),
        allowed_values(S + "customers", "city", CANONICAL_CITIES | {UNKNOWN_CITY}, severity=WARNING),
        allowed_values(S + "branches", "city", CANONICAL_CITIES, severity=WARNING),
    ]

    # -- dates ------------------------------------------------------------------------------
    checks += [
        not_future(S + "sales", "sale_datetime"),
        not_future(S + "service_orders", "opened_at"),
        not_future(S + "payments", "payment_datetime"),
        not_future(S + "customer_feedback", "feedback_date"),
        not_future(S + "customers", "registration_date", severity=WARNING),
        condition("plausible_sale_date", S + "sales", "sale_datetime < DATE '2015-01-01'", WARNING,
                  "sale_datetime", "sale_datetime must not be implausibly old"),
        condition("closed_after_opened", S + "service_orders", "closed_at < opened_at", CRITICAL,
                  "closed_at", "service order must close after it opens"),
        condition("completed_has_close_time", S + "service_orders",
                  "order_status = 'completed' AND closed_at IS NULL", CRITICAL, "closed_at",
                  "completed service orders must have a close time"),
    ]

    # -- quantities and money -------------------------------------------------------------
    checks += [
        positive(S + "sales", "quantity"),
        non_negative(S + "sales", "unit_price"),
        non_negative(S + "sales", "unit_cost"),
        non_negative(S + "sales", "discount_amount"),
        condition("discount_within_line_value", S + "sales", "discount_amount > quantity * unit_price",
                  CRITICAL, "discount_amount", "discount must not exceed the line value"),
        positive(S + "service_items", "quantity"),
        non_negative(S + "service_items", "unit_price"),
        positive(S + "payments", "amount"),
        condition("currency_is_gel", S + "payments", "currency <> 'GEL'", CRITICAL, "currency",
                  "all payments must be in GEL"),
        condition("rating_in_range", S + "customer_feedback", "rating NOT BETWEEN 1 AND 5", CRITICAL,
                  "rating", "rating must be between 1 and 5"),
        condition("price_above_cost", S + "products", "list_price < unit_cost", WARNING, "list_price",
                  "list price should not be below unit cost"),
    ]

    # -- completeness of optional attributes (tolerances) ------------------------------
    checks += [
        not_null(S + "customers", "email", WARNING, max_failed_ratio=0.10),
        not_null(S + "customers", "registration_date", WARNING, max_failed_ratio=0.01),
        not_null(S + "vehicles", "model_year", WARNING, max_failed_ratio=0.02),
        not_null(S + "products", "list_price", WARNING, max_failed_ratio=0.0),
        not_null(S + "customer_feedback", "rating", INFO, max_failed_ratio=0.25),
        condition("city_known", S + "customers", f"city = '{UNKNOWN_CITY}'", WARNING, "city",
                  "customer city should be known (at most 5% unknown)", max_failed_ratio=0.05),
    ]

    # -- cross-table business consistency ------------------------------------------------
    checks += [
        condition("completed_invoice_has_payment", S + "sales",
                  "order_status = 'completed' AND NOT EXISTS (SELECT 1 FROM staging.payments p "
                  "WHERE p.source_type = 'sale' AND p.payment_status = 'completed' "
                  "AND p.source_reference = staging.sales.invoice_number)",
                  WARNING, "invoice_number", "completed invoice lines should have a completed payment",
                  max_failed_ratio=0.02),
        condition("service_branch_offers_service", S + "service_orders",
                  "branch_id IN (SELECT branch_id FROM staging.branches WHERE branch_type = 'sales_only')",
                  WARNING, "branch_id", "service orders should not be booked at sales-only branches"),
    ]
    return checks


def source_stage_results(results: dict[str, CleanResult], raw_rows: dict[str, int]) -> list[CheckResult]:
    """Turn cleaning outcomes into measured source-stage checks."""
    out: list[CheckResult] = []
    for table, r in results.items():
        total = raw_rows[table]
        for reason, n in r.rejected_by_reason.items():
            out.append(CheckResult(f"rejected_{reason}", table, "source", "FAIL", WARNING, int(n), total,
                                   f"{n:,} raw rows rejected and quarantined ({reason})"))
        for fix, n in sorted(r.fixes.items()):
            out.append(CheckResult(f"fixed_{fix}", table, "source", "FAIL", INFO, int(n), total,
                                   f"{n:,} values repaired automatically ({fix})"))

        invalid = sum(n for reason, n in r.rejected_by_reason.items() if reason not in DUPLICATE_REASONS)
        rate = invalid / total if total else 0.0
        if rate > REJECTION_RATE_CRITICAL:
            severity, status = CRITICAL, "FAIL"
        elif rate > REJECTION_RATE_WARNING:
            severity, status = WARNING, "FAIL"
        else:
            severity, status = INFO, "PASS"
        out.append(CheckResult("invalid_row_rate", table, "source", status, severity, invalid, total,
                               f"{rate:.2%} of raw rows invalid (warning > {REJECTION_RATE_WARNING:.0%}, "
                               f"critical > {REJECTION_RATE_CRITICAL:.0%})"))
    return out


def schema_contract_result(table: str, error: str | None) -> CheckResult:
    if error:
        return CheckResult("schema_contract", table, "source", "FAIL", CRITICAL, 0, None, error)
    return CheckResult("schema_contract", table, "source", "PASS", INFO, 0, None,
                       "file present with all required columns")
