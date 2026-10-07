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


# ====================================================================== warehouse
def _same(name: str, table: str, left_sql: str, right_sql: str, description: str, tolerance: float = 0.0) -> Check:
    sql = f"SELECT CASE WHEN abs(({left_sql}) - ({right_sql})) <= {tolerance} THEN 0 ELSE 1 END"
    return Check(name, table, CRITICAL, sql, None, description)


def warehouse_checks() -> list[Check]:
    """Run after the star schema is built: reconciliation, SCD2 integrity, unknown-member usage."""
    checks: list[Check] = []
    row_pairs = [("sales", "fact_sales"), ("service_orders", "fact_service_orders"),
                 ("service_items", "fact_service_items"), ("payments", "fact_payments"),
                 ("customer_feedback", "fact_customer_feedback")]
    for src, fact in row_pairs:
        checks.append(_same("reconcile_row_count", f"dw.{fact}", f"SELECT count(*) FROM staging.{src}",
                            f"SELECT count(*) FROM dw.{fact}", f"row count must equal staging.{src}"))
    checks += [
        _same("reconcile_net_amount", "dw.fact_sales",
              "SELECT COALESCE(sum(ROUND(quantity * unit_price - discount_amount, 2)), 0) FROM staging.sales",
              "SELECT COALESCE(sum(net_amount), 0) FROM dw.fact_sales",
              "sales net amount must equal staging", tolerance=0.01),
        _same("reconcile_service_revenue", "dw.fact_service_items",
              "SELECT COALESCE(sum(ROUND(quantity * unit_price, 2)), 0) FROM staging.service_items",
              "SELECT COALESCE(sum(revenue_amount), 0) FROM dw.fact_service_items",
              "service line revenue (rounded per line, like an invoice) must equal staging", tolerance=0.01),
        _same("orders_match_items", "dw.fact_service_orders",
              "SELECT COALESCE(sum(total_revenue), 0) FROM dw.fact_service_orders",
              "SELECT COALESCE(sum(revenue_amount), 0) FROM dw.fact_service_items",
              "order-level revenue must equal the sum of its lines", tolerance=0.01),
        _same("reconcile_payment_amount", "dw.fact_payments",
              "SELECT COALESCE(sum(amount), 0) FROM staging.payments",
              "SELECT COALESCE(sum(amount), 0) FROM dw.fact_payments",
              "payment amounts must equal staging", tolerance=0.01),
        # SCD Type 2 integrity
        Check("one_current_version", "dw.dim_customer", CRITICAL,
              "SELECT count(*) FROM (SELECT customer_id FROM dw.dim_customer WHERE is_current "
              "GROUP BY customer_id HAVING count(*) > 1) d",
              "customer_id", "exactly one current version per customer"),
        condition("every_customer_has_current_version", "staging.customers",
                  "NOT EXISTS (SELECT 1 FROM dw.dim_customer d WHERE d.customer_id = staging.customers.customer_id "
                  "AND d.is_current)", CRITICAL, "customer_id", "every customer must have a current version"),
        Check("no_overlapping_versions", "dw.dim_customer", CRITICAL,
              "SELECT count(*) FROM dw.dim_customer a JOIN dw.dim_customer b "
              "ON a.customer_id = b.customer_id AND a.customer_key < b.customer_key "
              "AND a.valid_from <= b.valid_to AND b.valid_from <= a.valid_to",
              "valid_from", "SCD2 validity windows must not overlap"),
        # date dimension must be contiguous (required for time intelligence in Power BI)
        Check("contiguous_dates", "dw.dim_date", CRITICAL,
              "SELECT CASE WHEN count(*) = max(full_date) - min(full_date) + 1 THEN 0 ELSE 1 END FROM dw.dim_date",
              "full_date", "date dimension must have no gaps"),
        # unknown-member usage: transactions were validated, so -1 means a load bug (CRITICAL);
        # master-data gaps kept by policy show up as WARNING.
        condition("known_customer", "dw.fact_sales", "customer_key = -1", CRITICAL, "customer_key",
                  "sales must resolve to a known customer version"),
        condition("known_product", "dw.fact_sales", "product_key = -1", CRITICAL, "product_key",
                  "sales must resolve to a known product"),
        condition("known_category", "dw.fact_sales", "category_key = -1", WARNING, "category_key",
                  "sales of products with an unknown category"),
        condition("known_vehicle", "dw.fact_service_orders", "vehicle_key = -1", CRITICAL, "vehicle_key",
                  "service orders must resolve to a known vehicle"),
        condition("known_branch", "dw.fact_payments", "branch_key = -1", CRITICAL, "branch_key",
                  "payments must inherit a branch from their invoice / service order"),
        condition("known_home_branch", "dw.dim_employee", "employee_key <> -1 AND home_branch_name = 'Unknown branch'",
                  WARNING, "home_branch_id", "employees whose home branch is unknown"),
        non_negative("dw.fact_service_orders", "turnaround_hours"),
    ]
    # Logical foreign keys of the star schema, verified set-based (one query per relationship).
    for fact, column, dim in LOGICAL_FOREIGN_KEYS:
        checks.append(foreign_key(f"dw.{fact}", column, f"dw.{dim}"))
    for column in ("opened_date_key", "closed_date_key"):
        checks.append(foreign_key("dw.fact_service_orders", column, "dw.dim_date", "date_key"))
    return checks


LOGICAL_FOREIGN_KEYS = [
    ("fact_sales", "date_key", "dim_date"), ("fact_sales", "customer_key", "dim_customer"),
    ("fact_sales", "product_key", "dim_product"), ("fact_sales", "category_key", "dim_category"),
    ("fact_sales", "branch_key", "dim_branch"), ("fact_sales", "employee_key", "dim_employee"),
    ("fact_service_orders", "customer_key", "dim_customer"), ("fact_service_orders", "vehicle_key", "dim_vehicle"),
    ("fact_service_orders", "branch_key", "dim_branch"), ("fact_service_orders", "employee_key", "dim_employee"),
    ("fact_service_items", "service_order_id", "fact_service_orders"),
    ("fact_service_items", "product_key", "dim_product"), ("fact_service_items", "category_key", "dim_category"),
    ("fact_service_items", "branch_key", "dim_branch"), ("fact_service_items", "date_key", "dim_date"),
    ("fact_payments", "date_key", "dim_date"), ("fact_payments", "customer_key", "dim_customer"),
    ("fact_payments", "branch_key", "dim_branch"),
    ("fact_customer_feedback", "date_key", "dim_date"), ("fact_customer_feedback", "customer_key", "dim_customer"),
    ("fact_customer_feedback", "branch_key", "dim_branch"),
]
