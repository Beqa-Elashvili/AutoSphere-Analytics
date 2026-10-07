"""Transform: clean, normalize and validate each source table row by row.

Processing per table:
  1. drop exact duplicate rows
  2. normalize / parse every column (IDs, dates, money, categories, cities)
  3. apply business rules -> a row is rejected with the FIRST rule it fails
  4. check references against already-cleaned parent tables
  5. de-duplicate on the business key (first valid occurrence wins)

Policy (see docs/etl.md):
  * transaction rows with an invalid key, measure or date are REJECTED
    (quarantined with a reason, never silently dropped)
  * master rows are NOT rejected for a bad attribute: the value is set to NULL,
    or an unresolved reference is kept and flagged for the DQ report, because
    rejecting a product or employee would also drop all of its valid transactions
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from etl.sources import BUSINESS_KEYS, LOAD_ORDER, SOURCE_COLUMNS
from etl.transform.normalize import (
    blank_to_na, changed_mask, clean_text, fix_shouting, normalize_category, normalize_city,
    normalize_id, parse_bool, parse_date, parse_datetime, parse_decimal, parse_int,
)

EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"


@dataclass
class CleanResult:
    table: str
    clean: pd.DataFrame
    rejected: pd.DataFrame                       # record_key, reason, raw_record
    fixes: dict[str, int] = field(default_factory=dict)

    @property
    def rejected_by_reason(self) -> dict[str, int]:
        return self.rejected.reason.value_counts().to_dict()


@dataclass
class CleanContext:
    as_of: date                                  # anything after this is a future date
    keys: dict[str, set] = field(default_factory=dict)


class TableCleaner:
    """Accumulates normalized columns, rejection reasons and fix statistics for one table."""

    def __init__(self, table: str, raw: pd.DataFrame, ctx: CleanContext):
        self.table, self.ctx = table, ctx
        self.raw = raw.reset_index(drop=True)
        self.df = pd.DataFrame(index=self.raw.index)
        self.reason = pd.Series(None, index=self.raw.index, dtype="object")
        self._fixes: dict[str, pd.Series] = {}
        self.reject(self.raw.duplicated(keep="first"), "exact_duplicate")

    # -- bookkeeping -----------------------------------------------------------
    def _mask(self, mask) -> pd.Series:
        return pd.Series(mask, index=self.raw.index).fillna(False).astype(bool)

    def reject(self, mask, reason: str) -> None:
        m = self._mask(mask) & self.reason.isna()
        self.reason[m] = reason

    def fix(self, name: str, mask) -> None:
        m = self._mask(mask)
        self._fixes[name] = self._fixes.get(name, pd.Series(False, index=self.raw.index)) | m

    @property
    def ok(self) -> pd.Series:
        return self.reason.isna()

    def is_future(self, s: pd.Series) -> pd.Series:
        return (s > pd.Timestamp(self.ctx.as_of) + pd.Timedelta(days=1)).fillna(False)

    # -- column helpers ----------------------------------------------------------
    def id(self, col: str, required: bool = True) -> pd.Series:
        v = normalize_id(self.raw[col])
        self.fix(f"{col}_reformatted", changed_mask(self.raw[col], v))
        if required:
            self.reject(v.isna(), f"missing_{col}")
        self.df[col] = v
        return v

    def text(self, col: str, required: bool = False, names: bool = False) -> pd.Series:
        v = fix_shouting(self.raw[col]) if names else clean_text(self.raw[col])
        self.fix(f"{col}_cleaned", changed_mask(self.raw[col], v))
        if required:
            self.reject(v.isna(), f"missing_{col}")
        self.df[col] = v
        return v

    def category(self, col: str, domain: str, required: bool = True) -> pd.Series:
        v, invalid = normalize_category(self.raw[col], domain)
        self.fix(f"{col}_normalized", changed_mask(self.raw[col], v))
        self.reject(invalid, f"invalid_{col}")
        if required:
            self.reject(v.isna(), f"missing_{col}")
        self.df[col] = v
        return v

    def timestamp(self, col: str, required: bool = True, reject_future: bool = True) -> pd.Series:
        raw = blank_to_na(self.raw[col])
        v = parse_datetime(self.raw[col])
        self.fix(f"{col}_reformatted", raw.notna() & ~raw.str.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$").fillna(True) & v.notna())
        self.reject(raw.notna() & v.isna(), "invalid_date")
        if required:
            self.reject(raw.isna(), f"missing_{col}")
        if reject_future:
            self.reject(self.is_future(v), "future_date")
        self.df[col] = v
        return v

    def date(self, col: str, required: bool = True, nullify_invalid: bool = False) -> pd.Series:
        """Dates on master data use nullify_invalid=True (bad/future value -> NULL, row kept)."""
        raw = blank_to_na(self.raw[col])
        v = parse_date(self.raw[col])
        self.fix(f"{col}_reformatted", raw.notna() & ~raw.str.match(r"^\d{4}-\d{2}-\d{2}$").fillna(True) & v.notna())
        bad = (raw.notna() & v.isna()) | self.is_future(v)
        if nullify_invalid:
            self.fix(f"{col}_invalid_nullified", bad)
            v = v.mask(bad)
        else:
            self.reject(raw.notna() & v.isna(), "invalid_date")
            self.reject(self.is_future(v), "future_date")
        if required:
            self.reject(v.isna(), f"missing_{col}")
        self.df[col] = v.dt.date.astype("object").where(v.notna(), None)
        return v

    def amount(self, col: str, allow_zero: bool = True, required: bool = True) -> pd.Series:
        raw = blank_to_na(self.raw[col])
        v = parse_decimal(self.raw[col])
        self.fix(f"{col}_reformatted", raw.notna() & raw.str.contains(",", regex=False).fillna(False) & v.notna())
        self.reject(raw.notna() & v.isna(), "non_numeric_amount")
        self.reject(v < 0, "negative_amount")
        if not allow_zero:
            self.reject(v == 0, "zero_amount")
        if required:
            self.reject(raw.isna(), f"missing_{col}")
        self.df[col] = v.round(2)
        return v

    def quantity(self, col: str, integer: bool = True) -> pd.Series:
        raw = blank_to_na(self.raw[col])
        v = parse_int(self.raw[col]) if integer else parse_decimal(self.raw[col])
        self.reject(raw.isna(), f"missing_{col}")
        self.reject(v.isna(), "invalid_quantity")
        self.reject(v < 0, "negative_quantity")
        self.reject(v == 0, "zero_quantity")
        self.df[col] = v
        return v

    def boolean(self, col: str, default: bool = True) -> pd.Series:
        v = parse_bool(self.raw[col])
        self.fix(f"{col}_defaulted", v.isna())
        v = v.fillna(default)
        self.df[col] = v
        return v

    def must_exist(self, col: str, parent: str, reason: str) -> None:
        """Reject rows whose (present) reference is not among the parent's cleaned keys."""
        v = self.df[col]
        self.reject(v.notna() & ~v.isin(self.ctx.keys[parent]), reason)

    # -- finish ------------------------------------------------------------------------
    def finish(self) -> CleanResult:
        key = BUSINESS_KEYS[self.table]
        dup_key = self.df[key].where(self.ok).duplicated(keep="first") & self.ok
        self.reject(dup_key, "duplicate_business_key")
        ok = self.ok
        clean = self.df.loc[ok, SOURCE_COLUMNS[self.table]].reset_index(drop=True)
        bad = self.raw.loc[~ok]
        rejected = pd.DataFrame({
            "record_key": bad[key].str.strip().values,
            "reason": self.reason[~ok].values,
            "raw_record": bad.to_dict("records"),
        })
        fixes = {k: int((m & ok).sum()) for k, m in self._fixes.items() if (m & ok).any()}
        self.ctx.keys[self.table] = set(clean[key])
        return CleanResult(self.table, clean, rejected, fixes)


# ====================================================================== master data
def clean_branches(raw, ctx):
    c = TableCleaner("branches", raw, ctx)
    c.id("branch_id")
    c.text("branch_name", required=True)
    city = normalize_city(c.raw["city"])
    c.fix("city_normalized", changed_mask(c.raw["city"], city))
    c.df["city"] = city
    c.text("region", required=True)
    c.category("branch_type", "branch_type")
    c.date("opened_date")
    c.boolean("is_active")
    return c.finish()


def clean_product_categories(raw, ctx):
    c = TableCleaner("product_categories", raw, ctx)
    c.id("category_id")
    c.text("category_name", required=True)
    c.category("business_line", "business_line")
    return c.finish()


def clean_products(raw, ctx):
    c = TableCleaner("products", raw, ctx)
    c.id("product_id")
    name = clean_text(c.raw["product_name"])
    shouting = name.str.isupper().fillna(False)
    c.fix("product_name_cleaned", changed_mask(c.raw["product_name"], name) | shouting)
    c.df["product_name"] = name.mask(shouting, name.str.title())
    c.reject(name.isna(), "missing_product_name")
    c.id("category_id")                        # unknown category is kept and flagged (DQ report)
    c.text("brand", required=True)
    cost = parse_decimal(c.raw["unit_cost"])
    c.reject(cost.isna() | (cost < 0), "invalid_unit_cost")
    c.df["unit_cost"] = cost.round(2)
    price = parse_decimal(c.raw["list_price"])
    bad_price = price.isna() | (price <= 0)
    c.fix("list_price_invalid_nullified", bad_price)
    c.df["list_price"] = price.mask(bad_price).round(2)
    c.date("launch_date")
    c.boolean("is_active")
    return c.finish()


def clean_employees(raw, ctx):
    c = TableCleaner("employees", raw, ctx)
    c.id("employee_id")
    c.text("first_name", required=True, names=True)
    c.text("last_name", required=True, names=True)
    c.category("role", "role")
    c.category("department", "department")
    c.id("branch_id")                          # unknown branch is kept and flagged (DQ report)
    c.date("hire_date")
    c.boolean("is_active")
    return c.finish()


def clean_customers(raw, ctx):
    c = TableCleaner("customers", raw, ctx)
    c.id("customer_id")
    ctype = c.category("customer_type", "customer_type")
    first = c.text("first_name", names=True)
    last = c.text("last_name", names=True)
    company = c.text("company_name")
    email = blank_to_na(c.raw["email"]).str.lower()
    invalid_email = email.notna() & ~email.str.match(EMAIL_RE).fillna(False)
    c.fix("email_invalid_nullified", invalid_email)
    c.fix("email_lowercased", changed_mask(c.raw["email"], email) & ~invalid_email)
    c.df["email"] = email.mask(invalid_email)
    c.text("phone")
    city = normalize_city(c.raw["city"])
    c.fix("city_normalized", changed_mask(c.raw["city"], city))
    c.fix("city_missing_defaulted", blank_to_na(c.raw["city"]).isna())
    c.df["city"] = city
    c.date("registration_date", required=False, nullify_invalid=True)
    c.category("loyalty_tier", "loyalty_tier")
    c.reject((ctype == "individual") & (first.isna() | last.isna()), "missing_customer_name")
    c.reject((ctype == "corporate") & company.isna(), "missing_company_name")
    return c.finish()


def clean_vehicles(raw, ctx):
    c = TableCleaner("vehicles", raw, ctx)
    c.id("vehicle_id")
    vin = normalize_id(c.raw["vin"])
    c.reject(vin.isna() | (vin.str.len() != 17), "invalid_vin")
    c.df["vin"] = vin
    c.text("make", required=True)
    c.text("model", required=True)
    year = parse_int(c.raw["model_year"])
    bad_year = year.isna() | (year < 1980) | (year > ctx.as_of.year + 1)
    c.fix("model_year_invalid_nullified", bad_year)
    c.df["model_year"] = year.mask(bad_year)
    c.category("fuel_type", "fuel_type")
    c.category("transmission", "transmission")
    c.id("customer_id")                        # unknown owner is kept and flagged (DQ report)
    c.date("registration_date", required=False, nullify_invalid=True)
    # Same VIN under several vehicle_ids: keep the earliest-registered id.
    ordered = c.df[c.ok].sort_values("vehicle_id")
    c.reject(c.df.index.isin(ordered.index[ordered.vin.duplicated()]), "duplicate_vin")
    return c.finish()


# ====================================================================== transactions
def clean_sales(raw, ctx):
    c = TableCleaner("sales", raw, ctx)
    for col in ("sale_line_id", "invoice_number", "customer_id", "product_id", "branch_id", "employee_id"):
        c.id(col)
    c.timestamp("sale_datetime")
    qty = c.quantity("quantity")
    price = c.amount("unit_price")
    c.amount("unit_cost")
    discount_raw = blank_to_na(c.raw["discount_amount"])
    discount = c.amount("discount_amount", required=False).fillna(0)
    c.fix("discount_missing_defaulted", discount_raw.isna())
    c.df["discount_amount"] = discount.round(2)
    c.reject(discount > qty * price, "discount_exceeds_value")
    c.category("sales_channel", "sales_channel")
    c.category("order_status", "sales_order_status")
    c.must_exist("customer_id", "customers", "orphan_customer_id")
    c.must_exist("product_id", "products", "orphan_product_id")
    c.must_exist("branch_id", "branches", "orphan_branch_id")
    c.must_exist("employee_id", "employees", "orphan_employee_id")
    return c.finish()


def clean_service_orders(raw, ctx):
    c = TableCleaner("service_orders", raw, ctx)
    for col in ("service_order_id", "vehicle_id", "customer_id", "branch_id", "employee_id"):
        c.id(col)
    c.category("service_type", "service_type")
    opened = c.timestamp("opened_at")
    closed = c.timestamp("closed_at", required=False)
    status = c.category("order_status", "service_order_status")
    c.reject((status == "completed") & closed.isna(), "completed_without_close")
    c.reject(closed < opened, "closed_before_opened")
    odo = parse_int(c.raw["odometer_km"])
    c.fix("odometer_invalid_nullified", odo < 0)
    c.df["odometer_km"] = odo.mask(odo < 0)
    c.must_exist("vehicle_id", "vehicles", "orphan_vehicle_id")
    c.must_exist("customer_id", "customers", "orphan_customer_id")
    c.must_exist("branch_id", "branches", "orphan_branch_id")
    c.must_exist("employee_id", "employees", "orphan_employee_id")
    return c.finish()


def clean_service_items(raw, ctx):
    c = TableCleaner("service_items", raw, ctx)
    c.id("service_item_id")
    c.id("service_order_id")
    itype = c.category("item_type", "item_type")
    product = c.id("product_id", required=False)
    c.reject((itype == "part") & product.isna(), "part_without_product")
    desc = clean_text(c.raw["description"])
    c.fix("description_missing_defaulted", desc.isna())
    c.df["description"] = desc.fillna("Unspecified")
    c.quantity("quantity", integer=False)
    c.amount("unit_price")
    c.amount("unit_cost")
    c.must_exist("product_id", "products", "orphan_product_id")
    c.must_exist("service_order_id", "service_orders", "orphan_service_order_id")
    return c.finish()


def clean_payments(raw, ctx):
    c = TableCleaner("payments", raw, ctx)
    c.id("payment_id")
    stype = c.category("source_type", "source_type")
    ref = c.id("source_reference")
    c.id("customer_id")
    c.timestamp("payment_datetime")
    c.amount("amount", allow_zero=False)
    c.category("payment_method", "payment_method")
    c.category("payment_status", "payment_status")
    cur_raw = blank_to_na(c.raw["currency"])
    currency = cur_raw.str.upper().fillna("GEL")
    c.fix("currency_normalized", changed_mask(c.raw["currency"], currency))
    c.fix("currency_missing_defaulted", cur_raw.isna())
    c.reject(currency != "GEL", "invalid_currency")
    c.df["currency"] = currency
    c.must_exist("customer_id", "customers", "orphan_customer_id")
    known = ((stype == "sale") & ref.isin(ctx.keys["_invoices"])) | \
            ((stype == "service") & ref.isin(ctx.keys["service_orders"]))
    c.reject(ref.notna() & stype.notna() & ~known.fillna(False), "orphan_source_reference")
    return c.finish()


def clean_customer_feedback(raw, ctx):
    c = TableCleaner("customer_feedback", raw, ctx)
    for col in ("feedback_id", "customer_id", "branch_id"):
        c.id(col)
    # Context references are optional: unresolved ones are dropped, feedback is kept.
    for col, parent in (("service_order_id", "service_orders"), ("invoice_number", "_invoices")):
        v = normalize_id(c.raw[col])
        unresolved = v.notna() & ~v.isin(ctx.keys[parent])
        c.fix(f"{col}_unresolved_nullified", unresolved)
        c.df[col] = v.mask(unresolved)
    c.date("feedback_date")
    c.category("channel", "feedback_channel")
    rating = parse_int(c.raw["rating"])
    bad = blank_to_na(c.raw["rating"]).notna() & (rating.isna() | (rating < 1) | (rating > 5)).fillna(True)
    c.fix("rating_out_of_range_nullified", bad)
    c.df["rating"] = rating.mask(bad)
    text = clean_text(c.raw["feedback_text"])
    c.reject(text.isna(), "empty_feedback_text")
    c.df["feedback_text"] = text
    c.must_exist("customer_id", "customers", "orphan_customer_id")
    c.must_exist("branch_id", "branches", "orphan_branch_id")
    return c.finish()


CLEANERS = {
    "branches": clean_branches,
    "product_categories": clean_product_categories,
    "products": clean_products,
    "employees": clean_employees,
    "customers": clean_customers,
    "vehicles": clean_vehicles,
    "sales": clean_sales,
    "service_orders": clean_service_orders,
    "service_items": clean_service_items,
    "payments": clean_payments,
    "customer_feedback": clean_customer_feedback,
}
assert list(CLEANERS) == LOAD_ORDER


def clean_all(raw: dict[str, pd.DataFrame], as_of: date) -> dict[str, CleanResult]:
    """Clean every table in dependency order (parents first)."""
    ctx = CleanContext(as_of=as_of)
    results = {}
    for table in LOAD_ORDER:
        results[table] = CLEANERS[table](raw[table], ctx)
        if table == "sales":
            ctx.keys["_invoices"] = set(results["sales"].clean.invoice_number)
    return results
