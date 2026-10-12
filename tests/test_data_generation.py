"""Tests for synthetic data generation: realism, internal consistency, injected defects."""
import hashlib
import re

import numpy as np
import pandas as pd
import pytest

from datagen import reference as ref
from datagen.corrupt import ISSUE_CATALOG, inject_quality_issues, serialize
from datagen.feedback_templates import SENTIMENTS, TEMPLATES, TOPICS
from datagen.generate import VOLUMES, generate_clean_datasets

SCALE = 0.05  # small but structurally complete dataset keeps tests fast


@pytest.fixture(scope="module")
def clean():
    return generate_clean_datasets(seed=42, scale=SCALE)


@pytest.fixture(scope="module")
def raw_and_manifest(clean):
    return inject_quality_issues(clean, seed=42)


# ---------------------------------------------------------------- volumes & reference data
def test_target_volumes_meet_project_requirements():
    assert VOLUMES["customers"] >= 5000
    assert VOLUMES["vehicles"] >= 2000
    assert VOLUMES["service_orders"] >= 10000
    assert VOLUMES["feedback"] >= 10000
    assert 30 <= len(ref.PRODUCTS) <= 50
    assert 10 <= len(ref.CATEGORIES) <= 20
    assert 5 <= len(ref.BRANCHES) <= 10


def test_employee_headcount_in_expected_range(clean):
    assert 50 <= len(clean["employees"]) <= 100  # staffing does not scale with volume


def test_generation_is_reproducible():
    a = generate_clean_datasets(seed=7, scale=0.02)
    b = generate_clean_datasets(seed=7, scale=0.02)
    for table in ("customers", "sales", "payments", "customer_feedback"):
        pd.testing.assert_frame_equal(a[table], b[table])


def test_different_seed_gives_different_data():
    a = generate_clean_datasets(seed=1, scale=0.02)
    b = generate_clean_datasets(seed=2, scale=0.02)
    assert not a["sales"].equals(b["sales"])


# ---------------------------------------------------------------- clean data consistency
def _ids(df, col):
    return set(df[col])


def test_clean_foreign_keys_all_resolve(clean):
    c = clean
    fks = [
        ("products", "category_id", "product_categories", "category_id"),
        ("employees", "branch_id", "branches", "branch_id"),
        ("vehicles", "customer_id", "customers", "customer_id"),
        ("sales", "customer_id", "customers", "customer_id"),
        ("sales", "product_id", "products", "product_id"),
        ("sales", "branch_id", "branches", "branch_id"),
        ("sales", "employee_id", "employees", "employee_id"),
        ("service_orders", "vehicle_id", "vehicles", "vehicle_id"),
        ("service_orders", "employee_id", "employees", "employee_id"),
        ("service_items", "service_order_id", "service_orders", "service_order_id"),
        ("customer_feedback", "customer_id", "customers", "customer_id"),
        ("customer_feedback", "branch_id", "branches", "branch_id"),
    ]
    for child, col, parent, pcol in fks:
        orphans = _ids(c[child], col) - _ids(c[parent], pcol)
        assert not orphans, f"{child}.{col} has orphans: {list(orphans)[:3]}"


def test_clean_business_keys_are_unique(clean):
    keys = {"customers": "customer_id", "vehicles": "vin", "sales": "sale_line_id",
            "service_orders": "service_order_id", "payments": "payment_id", "customer_feedback": "feedback_id"}
    for table, key in keys.items():
        assert clean[table][key].is_unique, table


def test_transactions_fall_inside_business_period(clean):
    s = clean["sales"].sale_datetime
    assert s.min().date() >= ref.START_DATE and s.max().date() <= ref.END_DATE


def test_customers_never_buy_before_registering(clean):
    reg = clean["customers"].set_index("customer_id").registration_date
    s = clean["sales"]
    assert (s.customer_id.map(reg) <= s.sale_datetime.dt.date).all()


def test_products_never_sold_before_launch(clean):
    launch = clean["products"].set_index("product_id").launch_date
    s = clean["sales"]
    assert (s.product_id.map(launch) <= s.sale_datetime.dt.date).all()


def test_service_order_lifecycle_rules(clean):
    o = clean["service_orders"]
    done = o[o.order_status == "completed"]
    assert done.closed_at.notna().all()
    assert (done.closed_at >= done.opened_at).all()
    assert o[o.order_status != "completed"].closed_at.isna().all()


def test_branch_types_are_respected(clean):
    btype = dict(zip(clean["branches"].branch_id, clean["branches"].branch_type))
    assert not any(btype[b] == "service_only" for b in clean["sales"].branch_id.unique())
    assert not any(btype[b] == "sales_only" for b in clean["service_orders"].branch_id.unique())


def test_sales_line_values_are_valid(clean):
    s = clean["sales"]
    assert (s.quantity > 0).all()
    assert (s.discount_amount <= s.quantity * s.unit_price).all()
    assert (s.unit_cost >= 0).all()


def test_completed_payments_match_invoice_totals(clean):
    s = clean["sales"]
    totals = (s[s.order_status != "cancelled"]
              .assign(net=s.quantity * s.unit_price - s.discount_amount)
              .groupby("invoice_number").net.sum())
    p = clean["payments"]
    paid = p[(p.source_type == "sale") & (p.payment_status == "completed")].groupby("source_reference").amount.sum()
    diff = (totals - paid.reindex(totals.index).fillna(0)).abs()
    assert (diff < 0.05).all(), diff[diff >= 0.05].head()


def test_warranty_work_is_free_of_charge(clean):
    items = clean["service_items"].merge(clean["service_orders"][["service_order_id", "service_type"]])
    assert (items[items.service_type == "warranty"].unit_price == 0).all()


# ---------------------------------------------------------------- feedback
def test_feedback_is_bilingual_with_complete_labels(clean):
    fb, labels = clean["customer_feedback"], clean["_feedback_labels"]
    georgian = fb.feedback_text.str.contains(r"[Ⴀ-ჿ]", regex=True)
    assert 0.4 < georgian.mean() < 0.8
    assert set(labels.feedback_id) == set(fb.feedback_id)
    assert set(labels.true_sentiment) <= set(SENTIMENTS)
    assert set(labels.true_topic) <= set(TOPICS)


def test_every_template_key_uses_known_labels():
    for topic, sentiment in TEMPLATES:
        assert topic in TOPICS and sentiment in SENTIMENTS
        assert TEMPLATES[(topic, sentiment)]["en"] and TEMPLATES[(topic, sentiment)]["ka"]


# ---------------------------------------------------------------- serialization & defects
def test_serialize_produces_csv_style_text():
    df = pd.DataFrame({"flag": [True, False], "amount": [1.5, np.nan],
                       "day": [pd.Timestamp("2025-01-02").date(), None],
                       "rating": pd.array([4, None], dtype="Int64")})
    out = serialize(df)
    assert out.to_dict("list") == {"flag": ["true", "false"], "amount": ["1.50", ""],
                                   "day": ["2025-01-02", ""], "rating": ["4", ""]}


def test_manifest_only_uses_catalogued_issues(raw_and_manifest):
    _, manifest = raw_and_manifest
    used = {issue for issues in manifest.values() for issue in issues}
    assert used <= set(ISSUE_CATALOG)
    assert len(used) >= 25, "expected a broad range of defect types"


def test_raw_sales_contain_the_injected_defects(raw_and_manifest, clean):
    raw, manifest = raw_and_manifest
    s = raw["sales"]
    assert len(s) == len(clean["sales"]) + manifest["sales"]["exact_duplicate"]
    assert s.duplicated().sum() >= manifest["sales"]["exact_duplicate"]
    assert s.quantity.str.startswith("-").sum() >= manifest["sales"]["negative_quantity"]
    assert (~s.product_id.isin(clean["products"].product_id)).sum() >= manifest["sales"]["orphan_product_id"]
    assert s.sale_datetime.str.match(r"^\d{2}[./]\d{2}[./]\d{4}").any(), "non-ISO dates expected"


def test_raw_customers_have_messy_cities(raw_and_manifest):
    raw, _ = raw_and_manifest
    canonical = set(ref.CITIES)
    assert (~raw["customers"].city.isin(canonical)).sum() > 0


def test_raw_values_are_all_text(raw_and_manifest):
    raw, _ = raw_and_manifest
    for table, df in raw.items():
        assert all(df[c].map(type).eq(str).all() for c in df.columns), table


def test_csv_round_trip_preserves_georgian_text(raw_and_manifest, tmp_path):
    raw, _ = raw_and_manifest
    path = tmp_path / "customer_feedback.csv"
    raw["customer_feedback"].to_csv(path, index=False, encoding="utf-8")
    back = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    pd.testing.assert_frame_equal(back, raw["customer_feedback"])


# ---------------------------------------------------------------- neutrality / privacy
def test_no_real_company_names_and_synthetic_contacts_only(raw_and_manifest):
    raw, _ = raw_and_manifest
    blob = " ".join(" ".join(df.astype(str).agg(" ".join, axis=1)) for df in raw.values()).lower()
    # Real company names must never appear. They are stored as SHA-256 hashes, so the
    # project itself never contains the name it guards against.
    forbidden = {"76f8a619ba377bb82121dc2c3bf5e5b9adb6449cc0f610ac929c3468d1ca1e05"}
    words = set(re.findall(r"[a-z]+", blob))
    assert not {hashlib.sha256(w.encode()).hexdigest() for w in words} & forbidden
    emails = raw["customers"].email
    real = emails[(emails != "") & emails.str.contains("@")]
    assert real.str.lower().str.endswith("@example.com").all()
    assert re.fullmatch(r"\+995 5\d{2} \d{2} \d{2} \d{2}", raw["customers"].phone.iloc[0])
