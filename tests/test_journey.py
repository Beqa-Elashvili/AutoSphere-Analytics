"""Data Journey page: safe rendering and numbers that come from the real data."""
import json

import pytest

from reporting.journey import collect, render


def fake() -> dict:
    return {"run_id": 1, "lineage": [{"table": "sales", "raw": 10, "clean": 8, "quarantined": 2}],
            "reasons": [{"reason": "negative_quantity", "source_table": "sales", "n": 2}],
            "examples": {"city_variants": [{"value": "</script><script>alert(1)</script>", "n": 1}], "city_after": 1,
                         "dates": [], "negative": {"id": "SL1", "quantity": "-2", "reason": "negative_quantity",
                                                   "raw_record": "{}", "in_staging": 0}},
            "gates": [], "star": {}, "revenue": {"warehouse": 1, "kpi_views": 1, "power_bi": 1},
            "ytd": {"current_year": 2026, "ytd_to": "2026-09-30", "revenue_yoy_pct": 1.0},
            "naive_full_year_pct": None, "kutaisi": None, "turnaround": [],
            "ai": {"labelled": 0, "total": 0, "methods": [], "anomalies": []}}


def test_page_is_bilingual_self_contained_and_injection_safe():
    html = render(fake())
    assert "მონაცემების გზა" in html and "Data Journey" in html
    assert "<script src" not in html and "https://" not in html             # works offline
    assert "</script><script>alert(1)" not in html                          # cannot break out of the data block
    payload = html.split("const DATA = ", 1)[1].split(";\n", 1)[0]
    assert json.loads(payload.replace("<\/", "</"))["run_id"] == 1
    assert "innerHTML" not in html                                          # text is set via textContent only


@pytest.mark.db
def test_journey_numbers_come_from_the_data(engine):
    conn = engine.raw_connection()
    try:
        d = collect(conn)
    finally:
        conn.rollback()
        conn.close()
    assert all(r["raw"] == r["clean"] + r["quarantined"] for r in d["lineage"])
    assert d["examples"]["negative"]["reason"] == "negative_quantity"
    assert d["examples"]["negative"]["in_staging"] == 0
    assert len(d["examples"]["city_variants"]) > 1 and d["examples"]["city_after"] > 0
    assert d["revenue"]["warehouse"] == d["revenue"]["kpi_views"] == d["revenue"]["power_bi"]
    assert d["ytd"]["revenue_yoy_pct"] > 0 > d["naive_full_year_pct"]
