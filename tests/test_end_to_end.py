"""End-to-end acceptance: the platform-wide checklist (scripts/validate_end_to_end.py) passes.

Uses --skip-pipeline semantics: validates the database left by the last pipeline run, so it
is fast and never changes data. The pipeline itself is exercised by tests/test_etl.py.
"""
import pytest

from scripts.validate_end_to_end import Result, to_markdown, validate


def test_markdown_marks_failures_and_counts():
    md = to_markdown([Result("Lineage", "a", True, "ok"), Result("AI", "b", False, "bad")], "header")
    assert "| ✅ | Lineage | a | ok |" in md and "| ❌ | AI | b | bad |" in md
    assert "**1/2 checks passed.**" in md


@pytest.mark.db
def test_every_layer_passes_end_to_end(engine, tmp_path, monkeypatch):
    import reporting.job as job
    from datetime import date
    monkeypatch.setattr(job, "OUT_DIR", tmp_path)          # do not overwrite the user's latest report
    results = validate(engine, date.today())
    failed = [f"{r.layer}: {r.check} ({r.evidence})" for r in results if not r.passed]
    assert not failed, failed
    assert {r.layer for r in results} >= {"Lineage", "Data quality", "AI", "Power BI", "Business", "Reporting"}
