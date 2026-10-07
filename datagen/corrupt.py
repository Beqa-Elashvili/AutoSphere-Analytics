"""Inject realistic data-quality problems into clean datasets.

Clean typed data is first serialized to strings (as a CSV export would be),
then defects are injected. Each defect touches a distinct row, so the manifest
counts are exact and Phase 5 can verify the DQ framework catches them.

Expected handling per issue (implemented by the ETL in Phases 4-5):
  normalize   -> value is fixable (casing, spelling, format) and is repaired
  reject      -> row is invalid and goes to audit.rejected_rows
  deduplicate -> extra copy is removed, one row is kept
  nullify     -> bad optional value is set to NULL, row is kept
"""
from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd

from datagen.reference import CITY_VARIANTS

ISSUE_CATALOG: dict[str, tuple[str, str]] = {
    "exact_duplicate":         ("Row repeated verbatim (double export / retry)", "deduplicate"),
    "duplicate_id_variant":    ("Same business key, cosmetic differences (casing/whitespace)", "deduplicate"),
    "duplicate_vin":           ("Same VIN registered under a second vehicle_id", "deduplicate"),
    "city_variant":            ("Misspelled / mis-cased / Georgian-script city name", "normalize"),
    "missing_city":            ("City is empty", "normalize"),
    "category_case_variant":   ("Categorical value with wrong casing/spelling", "normalize"),
    "text_case_variant":       ("Name in ALL CAPS / lowercase / padded with spaces", "normalize"),
    "date_format_variant":     ("Date in a non-ISO format (day-first)", "normalize"),
    "id_format_variant":       ("Foreign key in lowercase or padded with spaces", "normalize"),
    "decimal_comma":           ("Money written with a decimal comma", "normalize"),
    "currency_case_variant":   ("Currency code mis-cased or padded", "normalize"),
    "missing_email":           ("Email is empty", "nullify"),
    "invalid_email":           ("Email is malformed", "nullify"),
    "missing_model_year":      ("Vehicle model year is empty", "reject"),
    "invalid_date":            ("Unparseable date", "reject"),
    "future_date":             ("Date after the data extraction date", "reject"),
    "orphan_customer_id":      ("customer_id does not exist", "reject"),
    "missing_customer_id":     ("customer_id is empty", "reject"),
    "orphan_product_id":       ("product_id does not exist", "reject"),
    "orphan_branch_id":        ("branch_id does not exist", "reject"),
    "missing_branch_id":       ("branch_id is empty", "reject"),
    "orphan_employee_id":      ("employee_id does not exist", "reject"),
    "orphan_vehicle_id":       ("vehicle_id does not exist", "reject"),
    "orphan_category_id":      ("category_id does not exist", "reject"),
    "orphan_service_order_id": ("service_order_id does not exist", "reject"),
    "orphan_source_reference": ("Payment references an unknown invoice / service order", "reject"),
    "negative_quantity":       ("Quantity below zero", "reject"),
    "zero_quantity":           ("Quantity equals zero", "reject"),
    "negative_amount":         ("Negative money value", "reject"),
    "zero_amount":             ("Payment amount equals zero", "reject"),
    "non_numeric_amount":      ("Money value is text such as 'N/A'", "reject"),
    "discount_exceeds_value":  ("Discount larger than the line value", "reject"),
    "invalid_currency":        ("Currency other than GEL", "reject"),
    "closed_before_opened":    ("Service order closed before it was opened", "reject"),
    "completed_without_close": ("Completed service order with no close time", "reject"),
    "part_without_product":    ("Part line has no product_id", "reject"),
    "empty_feedback_text":     ("Feedback text empty or whitespace", "reject"),
    "rating_out_of_range":     ("Rating outside 1-5", "nullify"),
}

DATE_FORMATS = ["%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%b-%Y"]
DATETIME_FORMATS = ["%d.%m.%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]


# ---------------------------------------------------------------------- serialization
def _to_str(value) -> str:
    if value is None or value is pd.NA or value is pd.NaT or (isinstance(value, float) and np.isnan(value)):
        return ""
    if isinstance(value, (bool, np.bool_)):
        return "true" if value else "false"
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (float, np.floating)):
        return f"{value:.2f}"
    return str(value)


def serialize(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a typed frame to the all-text form of a CSV export."""
    return pd.DataFrame({c: [_to_str(v) for v in df[c].tolist()] for c in df.columns})


# ---------------------------------------------------------------------- injector
class Corruptor:
    def __init__(self, rng: np.random.Generator):
        self.rng = rng
        self.manifest: dict[str, dict[str, int]] = {}
        self._touched: dict[str, set] = {}

    # -- primitives --------------------------------------------------------------
    def _pick(self, table: str, df: pd.DataFrame, frac: float, mask=None, minimum: int = 1) -> list:
        """Choose distinct, not-yet-corrupted rows (optionally restricted by mask)."""
        touched = self._touched.setdefault(table, set())
        candidates = df.index if mask is None else df.index[mask]
        candidates = [i for i in candidates if i not in touched]
        n = min(len(candidates), max(minimum, int(round(len(df) * frac))))
        chosen = list(self.rng.choice(candidates, size=n, replace=False)) if n else []
        touched.update(chosen)
        return chosen

    def _log(self, table: str, issue: str, n: int) -> None:
        assert issue in ISSUE_CATALOG, issue
        if n:
            t = self.manifest.setdefault(table, {})
            t[issue] = t.get(issue, 0) + n

    def apply(self, table, df, issue, frac, column, fn, mask=None, minimum=1):
        rows = self._pick(table, df, frac, mask, minimum)
        for i in rows:
            df.at[i, column] = fn(df.at[i, column])
        self._log(table, issue, len(rows))
        return rows

    def _choice(self, options):
        return options[int(self.rng.integers(len(options)))]

    def reformat_date(self, value: str) -> str:
        if not value:
            return value
        if " " in value:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime(self._choice(DATETIME_FORMATS))
        return datetime.strptime(value, "%Y-%m-%d").strftime(self._choice(DATE_FORMATS))

    def future(self, value: str) -> str:
        year = str(int(self.rng.integers(2028, 2032)))
        return year + value[4:8] + "28" + value[10:]   # day 28 keeps the date valid

    def case_variant(self, value: str) -> str:
        return self._choice([value.upper(), value.title(), value.replace("_", " "), f" {value} "])

    def orphan(self, prefix: str, width: int) -> callable:
        return lambda _: f"{prefix}{int(self.rng.integers(10 ** (width - 1) * 9, 10 ** width))}"

    def duplicates(self, table: str, df: pd.DataFrame, frac: float, transform=None, issue="exact_duplicate"):
        """Append copies of random rows at random positions in the file."""
        idx = self.rng.choice(df.index, size=max(1, int(round(len(df) * frac))), replace=False)
        dups = df.loc[idx].copy()
        if transform is not None:
            dups = transform(dups)
        self._log(table, issue, len(dups))
        order = np.concatenate([np.arange(len(df)), self.rng.uniform(0, len(df), len(dups))])
        out = pd.concat([df, dups], ignore_index=True)
        return out.iloc[np.argsort(order, kind="stable")].reset_index(drop=True)

    # -- per-table recipes -------------------------------------------------------------
    def branches(self, df):
        t = "branches"
        self.apply(t, df, "city_variant", 0.25, "city", lambda c: self._choice(CITY_VARIANTS.get(c, [c.upper()])))
        self.apply(t, df, "category_case_variant", 0.13, "branch_type", self.case_variant)
        self.apply(t, df, "date_format_variant", 0.25, "opened_date", self.reformat_date)
        return self.duplicates(t, df, 0.13)

    def product_categories(self, df):
        t = "product_categories"
        self.apply(t, df, "text_case_variant", 0.1, "category_name", lambda v: f"{v}  ")
        return self.duplicates(t, df, 0.08)

    def products(self, df):
        t = "products"
        self.apply(t, df, "orphan_category_id", 0.025, "category_id", lambda _: "CAT99")
        self.apply(t, df, "negative_amount", 0.025, "list_price", lambda v: f"-{v}")
        self.apply(t, df, "text_case_variant", 0.08, "product_name", lambda v: self._choice([v.upper(), f"  {v}"]))
        self.apply(t, df, "date_format_variant", 0.1, "launch_date", self.reformat_date)
        return self.duplicates(t, df, 0.05)

    def employees(self, df):
        t = "employees"
        self.apply(t, df, "orphan_branch_id", 0.02, "branch_id", lambda _: "BR99")
        self.apply(t, df, "category_case_variant", 0.06, "role", self.case_variant)
        self.apply(t, df, "text_case_variant", 0.04, "last_name", str.upper)
        self.apply(t, df, "date_format_variant", 0.1, "hire_date", self.reformat_date)
        return self.duplicates(t, df, 0.02)

    def customers(self, df):
        t = "customers"
        has_city = df.city.isin(list(CITY_VARIANTS))
        self.apply(t, df, "city_variant", 0.06, "city", lambda c: self._choice(CITY_VARIANTS[c]), mask=has_city)
        self.apply(t, df, "missing_city", 0.02, "city", lambda _: "")
        self.apply(t, df, "missing_email", 0.04, "email", lambda _: "")
        self.apply(t, df, "invalid_email", 0.005, "email", lambda e: e.replace("@", "#"))
        self.apply(t, df, "text_case_variant", 0.03, "last_name", lambda v: self._choice([v.upper(), v.lower()]),
                   mask=df.last_name != "")
        self.apply(t, df, "category_case_variant", 0.03, "customer_type", self.case_variant)
        self.apply(t, df, "category_case_variant", 0.02, "loyalty_tier", self.case_variant)
        self.apply(t, df, "date_format_variant", 0.15, "registration_date", self.reformat_date)
        self.apply(t, df, "future_date", 0.003, "registration_date", self.future)
        self.apply(t, df, "invalid_date", 0.002, "registration_date", lambda _: self._choice(["N/A", "2023-02-30", "unknown"]))
        df = self.duplicates(t, df, 0.01)

        def variant(d):
            d = d.copy()
            d["first_name"] = d.first_name.str.upper()
            d["email"] = d.email.str.upper()
            return d
        return self.duplicates(t, df, 0.005, variant, issue="duplicate_id_variant")

    def vehicles(self, df):
        t = "vehicles"
        self.apply(t, df, "orphan_customer_id", 0.005, "customer_id", self.orphan("CUS", 5))
        self.apply(t, df, "category_case_variant", 0.05, "fuel_type",
                   lambda f: self._choice([f.title(), f.upper(), {"petrol": "gasoline"}.get(f, f.upper())]))
        self.apply(t, df, "category_case_variant", 0.03, "transmission", str.title)
        self.apply(t, df, "missing_model_year", 0.01, "model_year", lambda _: "")
        self.apply(t, df, "date_format_variant", 0.1, "registration_date", self.reformat_date)

        def new_ids(d):
            d = d.copy()
            d["vehicle_id"] = [f"VEH{9 * 10 ** 4 + i}" for i in range(len(d))]
            return d
        df = self.duplicates(t, df, 0.005, new_ids, issue="duplicate_vin")
        return self.duplicates(t, df, 0.005)

    def sales(self, df):
        t = "sales"
        self.apply(t, df, "negative_quantity", 0.004, "quantity", lambda q: f"-{q}")
        self.apply(t, df, "zero_quantity", 0.001, "quantity", lambda _: "0")
        self.apply(t, df, "orphan_product_id", 0.003, "product_id", lambda _: self._choice(["PRD999", "PRD0X1", "PRD404"]))
        self.apply(t, df, "orphan_customer_id", 0.003, "customer_id", self.orphan("CUS", 5))
        self.apply(t, df, "missing_customer_id", 0.002, "customer_id", lambda _: "")
        self.apply(t, df, "orphan_branch_id", 0.002, "branch_id", lambda _: "BR99")
        self.apply(t, df, "orphan_employee_id", 0.002, "employee_id", self.orphan("EMP", 3))
        self.apply(t, df, "id_format_variant", 0.005, "customer_id", lambda v: self._choice([v.lower(), f" {v} "]))
        self.apply(t, df, "negative_amount", 0.002, "unit_price", lambda v: f"-{v}")
        self.apply(t, df, "non_numeric_amount", 0.001, "unit_price", lambda _: "N/A")
        self.apply(t, df, "decimal_comma", 0.005, "unit_price", lambda v: v.replace(".", ","))
        self.apply(t, df, "discount_exceeds_value", 0.001, "discount_amount", lambda _: "999999.00")
        self.apply(t, df, "date_format_variant", 0.10, "sale_datetime", self.reformat_date)
        self.apply(t, df, "future_date", 0.002, "sale_datetime", self.future)
        self.apply(t, df, "invalid_date", 0.001, "sale_datetime", lambda _: "not recorded")
        self.apply(t, df, "category_case_variant", 0.05, "sales_channel",
                   lambda v: self._choice([v.upper(), "In-Store" if v == "in_store" else v.title(), v.replace("_", " ")]))
        self.apply(t, df, "category_case_variant", 0.03, "order_status",
                   lambda v: self._choice([v.title(), v.upper(), "canceled" if v == "cancelled" else v.upper()]))
        return self.duplicates(t, df, 0.01)

    def service_orders(self, df):
        t = "service_orders"
        closed = df.closed_at != ""
        self.apply(t, df, "closed_before_opened", 0.003, "closed_at",
                   lambda v: (datetime.strptime(v, "%Y-%m-%d %H:%M:%S").replace(year=2023)).strftime("%Y-%m-%d %H:%M:%S"),
                   mask=closed)
        self.apply(t, df, "completed_without_close", 0.002, "closed_at", lambda _: "", mask=df.order_status == "completed")
        self.apply(t, df, "orphan_vehicle_id", 0.003, "vehicle_id", self.orphan("VEH", 5))
        self.apply(t, df, "missing_branch_id", 0.002, "branch_id", lambda _: "")
        self.apply(t, df, "category_case_variant", 0.04, "order_status",
                   lambda v: self._choice([v.title(), v.upper(), v.replace("_", " ").title()]))
        self.apply(t, df, "category_case_variant", 0.03, "service_type",
                   lambda v: self._choice([v.title(), v.replace("_", " "), v.replace("_", "-").title()]))
        self.apply(t, df, "date_format_variant", 0.08, "opened_at", self.reformat_date)
        self.apply(t, df, "future_date", 0.001, "opened_at", self.future, mask=~closed)
        return self.duplicates(t, df, 0.008)

    def service_items(self, df):
        t = "service_items"
        part = df.item_type == "part"
        self.apply(t, df, "orphan_service_order_id", 0.003, "service_order_id", self.orphan("SO", 7))
        self.apply(t, df, "part_without_product", 0.002, "product_id", lambda _: "", mask=part)
        self.apply(t, df, "orphan_product_id", 0.002, "product_id", lambda _: "PRD999", mask=part)
        self.apply(t, df, "negative_quantity", 0.003, "quantity", lambda q: f"-{q}")
        self.apply(t, df, "category_case_variant", 0.02, "item_type",
                   lambda v: self._choice([v.title(), v.upper(), "labour" if v == "labor" else v.upper()]))
        return self.duplicates(t, df, 0.008)

    def payments(self, df):
        t = "payments"
        self.apply(t, df, "negative_amount", 0.002, "amount", lambda v: f"-{v}")
        self.apply(t, df, "zero_amount", 0.001, "amount", lambda _: "0.00")
        self.apply(t, df, "non_numeric_amount", 0.0005, "amount", lambda _: "N/A")
        self.apply(t, df, "currency_case_variant", 0.03, "currency", lambda _: self._choice(["gel", "Gel", " GEL"]))
        self.apply(t, df, "invalid_currency", 0.001, "currency", lambda _: "USD")
        self.apply(t, df, "orphan_source_reference", 0.003, "source_reference",
                   lambda v: "INV-2099-000001" if v.startswith("INV") else "SO999999")
        self.apply(t, df, "category_case_variant", 0.04, "payment_method",
                   lambda v: self._choice([v.title(), v.upper(), "credit card" if v == "card" else v.replace("_", " ").title()]))
        self.apply(t, df, "category_case_variant", 0.02, "payment_status",
                   lambda v: self._choice([v.title(), v.upper(), "success" if v == "completed" else v.upper()]))
        self.apply(t, df, "date_format_variant", 0.08, "payment_datetime", self.reformat_date)
        self.apply(t, df, "future_date", 0.001, "payment_datetime", self.future)
        return self.duplicates(t, df, 0.007)

    def customer_feedback(self, df):
        t = "customer_feedback"
        self.apply(t, df, "empty_feedback_text", 0.007, "feedback_text", lambda _: self._choice(["", "   "]))
        self.apply(t, df, "rating_out_of_range", 0.005, "rating", lambda _: self._choice(["0", "6", "10"]))
        self.apply(t, df, "orphan_branch_id", 0.002, "branch_id", lambda _: "BR99")
        self.apply(t, df, "orphan_customer_id", 0.003, "customer_id", self.orphan("CUS", 5))
        self.apply(t, df, "date_format_variant", 0.10, "feedback_date", self.reformat_date)
        self.apply(t, df, "future_date", 0.002, "feedback_date", self.future)
        self.apply(t, df, "category_case_variant", 0.03, "channel",
                   lambda v: self._choice([v.upper(), v.replace("_", " ").title(), {"sms_survey": "SMS"}.get(v, v.title())]))
        return self.duplicates(t, df, 0.01)


def inject_quality_issues(clean: dict[str, pd.DataFrame], seed: int = 42):
    """Return (raw text datasets, manifest {table: {issue: count}})."""
    rng = np.random.default_rng(seed + 1)   # independent stream from clean generation
    corruptor = Corruptor(rng)
    raw = {}
    for table, df in clean.items():
        if table.startswith("_"):
            continue
        text_df = serialize(df)
        raw[table] = getattr(corruptor, table)(text_df)
    return raw, corruptor.manifest
