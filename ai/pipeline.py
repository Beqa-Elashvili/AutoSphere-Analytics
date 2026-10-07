"""NLP enrichment step: classify new/changed feedback and persist the results.

    staging.customer_feedback --(pending only)--> classifier --> dw.feedback_classification
                                                                       |
                                       warehouse build joins it into fact_customer_feedback

Runs in its own committed transaction BEFORE the warehouse build, so paid model
results are kept even if a later pipeline step fails.
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

from ai.classification.rule_based import RuleBasedClassifier
from ai.schema import Classification, text_hash
from common.config import Settings
from common.logging_config import get_logger
from etl.load.staging_loader import copy_frame

log = get_logger("ai.pipeline")

PENDING_SQL = """
SELECT f.feedback_id, f.feedback_text
FROM staging.customer_feedback f
LEFT JOIN dw.feedback_classification c ON c.feedback_id = f.feedback_id
WHERE c.feedback_id IS NULL                                  -- new feedback
   OR c.text_hash <> md5(f.feedback_text)                    -- edited feedback
   OR (%(external)s AND c.method <> 'gemini')                -- upgrade fallback labels
ORDER BY f.feedback_id
"""

UPSERT_SQL = """
INSERT INTO dw.feedback_classification
    (feedback_id, text_hash, language, sentiment, topic, confidence, method, model, classified_at)
SELECT feedback_id, text_hash, language, sentiment, topic, confidence, method, model, now()
FROM tmp_classification
ON CONFLICT (feedback_id) DO UPDATE SET
    text_hash = EXCLUDED.text_hash, language = EXCLUDED.language, sentiment = EXCLUDED.sentiment,
    topic = EXCLUDED.topic, confidence = EXCLUDED.confidence, method = EXCLUDED.method,
    model = EXCLUDED.model, classified_at = EXCLUDED.classified_at
"""


@dataclass
class EnrichmentResult:
    mode: str
    pending: int = 0
    classified: int = 0
    by_method: dict = field(default_factory=dict)
    provider_stats: dict = field(default_factory=dict)
    duration_s: float = 0.0


def get_classifier(settings: Settings):
    if settings.ai_mode == "external":
        from ai.classification.gemini import GeminiClassifier
        return GeminiClassifier(settings)
    return RuleBasedClassifier()


def split_budget(pending: list[tuple[str, str]], external: bool, budget: int):
    """Cost guard: at most `budget` items go to the paid provider in one run; the rest
    get local labels now and are upgraded automatically by later runs."""
    if not external:
        return [], pending
    return pending[:budget], pending[budget:]


def classify_pending(pending: list[tuple[str, str]], settings: Settings) -> tuple[list[Classification], dict]:
    external = settings.ai_mode == "external"
    to_model, to_local = split_budget(pending, external, settings.ai_max_external_per_run)
    results: list[Classification] = []
    stats: dict = {}
    if to_model:
        classifier = get_classifier(settings)
        results += classifier.classify_many(to_model)
        stats = dict(getattr(classifier, "stats", {}))
    if to_local:
        if external:
            log.warning("AI budget reached: %d items labelled locally, upgraded on a later run", len(to_local))
        results += RuleBasedClassifier().classify_many(to_local)
    return results, stats


def save_classifications(conn, results: list[Classification], texts: dict[str, str]) -> int:
    if not results:
        return 0
    df = pd.DataFrame([r.as_row() for r in results])
    df.insert(1, "text_hash", df.feedback_id.map(lambda fid: text_hash(texts[fid])))
    df = df[["feedback_id", "text_hash", "language", "sentiment", "topic", "confidence", "method", "model"]]
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE tmp_classification "
                    "(LIKE dw.feedback_classification INCLUDING DEFAULTS) ON COMMIT DROP")
        copy_frame(cur, "tmp_classification", df)
        cur.execute(UPSERT_SQL)
    return len(df)


def run_enrichment(engine, settings: Settings) -> EnrichmentResult:
    started = time.time()
    model = settings.ai_model if settings.ai_mode == "external" else "rules-v1"
    result = EnrichmentResult(mode=f"{settings.ai_mode}:{model}")
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(PENDING_SQL, {"external": settings.ai_mode == "external"})
            pending = [(fid, text) for fid, text in cur.fetchall()]
        result.pending = len(pending)
        log.info("NLP enrichment (%s): %d feedback item(s) need classification", result.mode, len(pending))
        if pending:
            results, result.provider_stats = classify_pending(pending, settings)
            result.classified = save_classifications(conn, results, dict(pending))
            result.by_method = dict(Counter(r.method for r in results))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    result.duration_s = time.time() - started
    log.info("NLP enrichment: classified %d (%s) in %.1fs %s", result.classified, result.by_method,
             result.duration_s, result.provider_stats or "")
    return result
