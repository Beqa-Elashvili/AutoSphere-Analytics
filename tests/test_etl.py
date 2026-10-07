"""ETL tests: normalizers, schema validation, cleaning rules, reconciliation, staging load."""
from datetime import date

import pandas as pd
import pytest

from datagen.corrupt import inject_quality_issues
from datagen.generate import generate_clean_datasets
from etl.extract.csv_extractor import SchemaValidationError, validate_columns
from etl.sources import BUSINESS_KEYS, SOURCE_COLUMNS
from etl.transform.cleaners import CleanContext, clean_all, clean_customers, clean_sales, clean_service_items
from etl.transform.mappings import ALLOWED
from etl.transform.normalize import (
    normalize_category, normalize_city, normalize_id, parse_date, parse_datetime, parse_decimal, parse_int,
)

AS_OF = date(2026, 10, 7)


def S(*values):
    return pd.Series(list(values), dtype="object")


# ---------------------------------------------------------------- normalizers
def test_parse_date_accepts_all_source_formats_day_first():
    out = parse_date(S("2025-03-04", "04.03.2025", "04/03/2025", "2025/03/04", "04-Mar-2025"))
    assert (out == pd.Timestamp("2025-03-04")).all()   # 04/03 is 4 March, never 3 April


def test_parse_date_returns_nat_for_invalid_values():
    out = parse_date(S("2023-02-30", "N/A", "unknown", "", "  "))
    assert out.isna().all()


def test_parse_datetime_formats():
    out = parse_datetime(S("2025-01-15 10:30:00", "2025-01-15T10:30:00", "15.01.2025 10:30", "15/01/2025 10:30:00"))
    assert (out == pd.Timestamp("2025-01-15 10:30")).all()


def test_parse_decimal_handles_commas_whitespace_and_text():
    out = parse_decimal(S("245.00", " 245,50 ", "1,245.00", "N/A", "", "-10"))
    assert out.tolist()[:3] == [245.0, 245.5, 1245.0]
    assert out.isna().tolist()[3:5] == [True, True]
    assert out.iloc[5] == -10


def test_parse_int_rejects_fractions():
    out = parse_int(S("4", "-2", "1.5", "x"))
    assert out.iloc[0] == 4 and out.iloc[1] == -2
    assert out.iloc[2:].isna().all()


def test_normalize_id_uppercases_and_strips():
    assert normalize_id(S(" cus00012 ", "PRD 001", "")).tolist()[:2] == ["CUS00012", "PRD001"]


@pytest.mark.parametrize("raw, expected", [
    ("In-Store", "in_store"), ("in store", "in_store"), ("ONLINE", "online"), (" Phone ", "phone"),
])
def test_normalize_category_maps_variants(raw, expected):
    values, invalid = normalize_category(S(raw), "sales_channel")
    assert values.iloc[0] == expected and not invalid.iloc[0]


def test_normalize_category_uses_synonyms_and_flags_unknown():
    values, invalid = normalize_category(S("canceled", "COMPLETED", "teleport"), "sales_order_status")
    assert values.tolist()[:2] == ["cancelled", "completed"]
    assert pd.isna(values.iloc[2]) and invalid.tolist() == [False, False, True]


def test_normalize_city_variants_and_unknown():
    out = normalize_city(S("tbilisi", "TBILISI", "Tbilsi", " Tbilisi ", "თბილისი", "Batum", "", "senaki"))
    assert out.tolist() == ["Tbilisi"] * 5 + ["Batumi", "Unknown", "Senaki"]


# ---------------------------------------------------------------- schema validation
def test_missing_required_column_stops_the_pipeline():
    df = pd.DataFrame({"branch_id": ["BR01"]})
    with pytest.raises(SchemaValidationError, match="missing required column"):
        validate_columns("branches", df)


def test_extra_columns_are_dropped_with_a_warning_and_headers_normalized():
    cols = {c.upper(): ["x"] for c in SOURCE_COLUMNS["product_categories"]}
    df, warnings = validate_columns("product_categories", pd.DataFrame({**cols, "legacy_flag": ["1"]}))
    assert list(df.columns) == SOURCE_COLUMNS["product_categories"]
    assert warnings and "legacy_flag" in warnings[0]


def test_empty_file_is_rejected():
    with pytest.raises(SchemaValidationError, match="no rows"):
        validate_columns("product_categories", pd.DataFrame(columns=SOURCE_COLUMNS["product_categories"]))


# ---------------------------------------------------------------- cleaning rules
def _ctx():
    return CleanContext(as_of=AS_OF, keys={
        "customers": {"CUS00001"}, "products": {"PRD001"}, "branches": {"BR01"}, "employees": {"EMP001"},
        "service_orders": {"SO000001"},
    })


def _sale(**overrides):
    row = dict(sale_line_id="SL1", invoice_number="INV-1", sale_datetime="2025-05-01 10:00:00",
               customer_id="CUS00001", product_id="PRD001", branch_id="BR01", employee_id="EMP001",
               quantity="2", unit_price="100.00", unit_cost="60.00", discount_amount="0.00",
               sales_channel="in_store", order_status="completed")
    row.update(overrides)
    return row


@pytest.mark.parametrize("overrides, reason", [
    ({"quantity": "-1"}, "negative_quantity"),
    ({"quantity": "0"}, "zero_quantity"),
    ({"unit_price": "N/A"}, "non_numeric_amount"),
    ({"unit_price": "-5.00"}, "negative_amount"),
    ({"discount_amount": "999.00"}, "discount_exceeds_value"),
    ({"sale_datetime": "2029-05-28 10:00:00"}, "future_date"),
    ({"sale_datetime": "not recorded"}, "invalid_date"),
    ({"customer_id": ""}, "missing_customer_id"),
    ({"customer_id": "CUS99999"}, "orphan_customer_id"),
    ({"product_id": "PRD999"}, "orphan_product_id"),
    ({"branch_id": "BR99"}, "orphan_branch_id"),
    ({"sales_channel": "teleport"}, "invalid_sales_channel"),
])
def test_invalid_sales_rows_are_rejected_with_reason(overrides, reason):
    result = clean_sales(pd.DataFrame([_sale(), _sale(sale_line_id="SL2", **overrides)]), _ctx())
    assert result.clean.sale_line_id.tolist() == ["SL1"]
    assert result.rejected.reason.tolist() == [reason]
    assert result.rejected.raw_record.iloc[0]["sale_line_id"] == "SL2"   # original values preserved


def test_fixable_sales_values_are_normalized_not_rejected():
    raw = pd.DataFrame([_sale(customer_id=" cus00001 ", unit_price="100,00", sale_datetime="01.05.2025 10:00",
                              sales_channel="In-Store", order_status="canceled")])
    result = clean_sales(raw, _ctx())
    row = result.clean.iloc[0]
    assert result.rejected.empty
    assert (row.customer_id, row.unit_price, row.sales_channel, row.order_status) == \
           ("CUS00001", 100.0, "in_store", "cancelled")
    assert row.sale_datetime == pd.Timestamp("2025-05-01 10:00")
    assert result.fixes["customer_id_reformatted"] == 1


def test_exact_duplicates_keep_one_copy():
    result = clean_sales(pd.DataFrame([_sale(), _sale(), _sale()]), _ctx())
    assert len(result.clean) == 1
    assert result.rejected.reason.tolist() == ["exact_duplicate", "exact_duplicate"]


def test_customer_master_data_is_repaired_not_rejected():
    base = dict(customer_id="CUS00001", customer_type="Individual", first_name="NINO", last_name="beridze",
                company_name="", email="Nino.Beridze1@Example.com", phone="+995 555 11 22 33",
                city="tbilisi", registration_date="2030-05-28", loyalty_tier="GOLD")
    variant = {**base, "customer_id": "cus00001", "email": "broken#example.com"}   # same key, cosmetic diff
    result = clean_customers(pd.DataFrame([base, variant]), _ctx())
    row = result.clean.iloc[0]
    assert len(result.clean) == 1 and result.rejected.reason.tolist() == ["duplicate_business_key"]
    assert (row.first_name, row.last_name, row.city, row.customer_type, row.loyalty_tier) == \
           ("Nino", "Beridze", "Tbilisi", "individual", "gold")
    assert row.email == "nino.beridze1@example.com"
    assert row.registration_date is None            # future date nullified, customer kept


def test_service_items_of_unknown_orders_are_rejected_and_parts_need_products():
    items = pd.DataFrame([
        dict(service_item_id="SI1", service_order_id="SO000001", item_type="Labour", product_id="",
             description="Labour", quantity="1.5", unit_price="95.00", unit_cost="40.00"),
        dict(service_item_id="SI2", service_order_id="SO000001", item_type="part", product_id="",
             description="Pads", quantity="1", unit_price="135.00", unit_cost="74.00"),
        dict(service_item_id="SI3", service_order_id="SO999999", item_type="labor", product_id="",
             description="Labour", quantity="1", unit_price="95.00", unit_cost="40.00"),
    ])
    result = clean_service_items(items, _ctx())
    assert result.clean.service_item_id.tolist() == ["SI1"]
    assert result.clean.item_type.iloc[0] == "labor"
    assert sorted(result.rejected.reason) == ["orphan_service_order_id", "part_without_product"]


# ---------------------------------------------------------------- end-to-end on generated data
@pytest.fixture(scope="module")
def pipeline_output():
    clean = generate_clean_datasets(seed=42, scale=0.05)
    raw, manifest = inject_quality_issues(clean, seed=42)
    return raw, manifest, clean_all(raw, AS_OF)


def test_self_contained_sales_defects_reconcile_exactly_with_manifest(pipeline_output):
    _, manifest, results = pipeline_output
    injected, rejected = manifest["sales"], results["sales"].rejected_by_reason
    for issue in ("exact_duplicate", "negative_quantity", "zero_quantity", "orphan_product_id",
                  "orphan_customer_id", "missing_customer_id", "orphan_branch_id", "orphan_employee_id",
                  "discount_exceeds_value", "future_date", "invalid_date", "non_numeric_amount"):
        assert rejected.get(issue, 0) == injected.get(issue, 0), issue


def test_no_rows_are_lost_unaccounted(pipeline_output):
    raw, _, results = pipeline_output
    for table, r in results.items():
        assert len(r.clean) + len(r.rejected) == len(raw[table]), table


def test_cleaned_output_satisfies_the_staging_contract(pipeline_output):
    _, _, results = pipeline_output
    domains = {("sales", "sales_channel"): "sales_channel", ("sales", "order_status"): "sales_order_status",
               ("service_orders", "order_status"): "service_order_status",
               ("payments", "payment_method"): "payment_method", ("customers", "loyalty_tier"): "loyalty_tier",
               ("customer_feedback", "channel"): "feedback_channel", ("service_items", "item_type"): "item_type"}
    for (table, col), domain in domains.items():
        assert set(results[table].clean[col].dropna()) <= ALLOWED[domain], (table, col)
    for table, key in BUSINESS_KEYS.items():
        assert results[table].clean[key].is_unique and results[table].clean[key].notna().all(), table
    assert (results["payments"].clean.currency == "GEL").all()
    assert results["customer_feedback"].clean.rating.dropna().between(1, 5).all()


# ---------------------------------------------------------------- database load
@pytest.mark.db
def test_staging_load_is_transactional(engine, pipeline_output):
    from etl.load.staging_loader import load_staging

    _, _, results = pipeline_output
    with engine.connect() as c:
        before = c.exec_driver_sql("SELECT count(*) FROM staging.sales").scalar()
    conn = engine.raw_connection()
    try:
        counts = load_staging(conn, {t: r.clean for t, r in results.items()})
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM staging.sales")
            assert cur.fetchone()[0] == counts["staging.sales"] == len(results["sales"].clean)
    finally:
        conn.rollback()          # TRUNCATE is transactional in PostgreSQL
        conn.close()
    with engine.connect() as c:
        assert c.exec_driver_sql("SELECT count(*) FROM staging.sales").scalar() == before
