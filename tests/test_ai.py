"""AI/NLP tests: local classifier, output contract, Gemini client behaviour (mocked), evaluation, warehouse."""
import hashlib
from types import SimpleNamespace

import pandas as pd
import pytest

from ai.classification import gemini as gemini_module
from ai.classification.gemini import GeminiClassifier
from ai.classification.rule_based import RuleBasedClassifier, detect_language
from ai.evaluation import evaluate, load_holdout
from ai.insights import template_insight
from ai.pipeline import split_budget
from ai.schema import LANGUAGES, SENTIMENTS, TOPICS, Classification, InvalidClassification, text_hash, validate
from common.config import load_settings

LOCAL = RuleBasedClassifier()


# ---------------------------------------------------------------- local classifier
def test_specification_example_is_negative_waiting_time_in_georgian():
    r = LOCAL.classify("X", "სერვისი კარგი იყო, მაგრამ ძალიან დიდხანს მომიწია ლოდინი.")
    assert (r.language, r.sentiment, r.topic) == ("ka", "negative", "waiting_time")
    assert 0 < r.confidence <= 1 and r.method == "rule_based"


@pytest.mark.parametrize("text, sentiment, topic", [
    ("The staff was rude and not interested in helping.", "negative", "staff"),
    ("Fair prices compared to other places.", "positive", "price"),
    ("The part was out of stock again.", "negative", "availability"),
    ("Waiting two weeks for a part that should be in stock.", "negative", "availability"),
    ("No waiting at all, everything was on time.", "positive", "waiting_time"),
    ("It took a bit longer than expected, but it was fine.", "neutral", "waiting_time"),
    ("This is unacceptable, I demand a refund.", "negative", "complaint"),
    ("Do you work on Sundays?", "neutral", "other"),
    ("ძალიან ძვირია, ფასები ისევ გაიზარდა.", "negative", "price"),
    ("პერსონალი ძალიან თავაზიანი და დამხმარე იყო.", "positive", "staff"),
    ("ლოდინი საერთოდ არ მომიწია, ყველაფერი დროულად გაკეთდა.", "positive", "waiting_time"),
    ("ნაწილი ისევ არ ჰქონდათ მარაგში.", "negative", "availability"),
])
def test_local_classifier_on_known_phrasings(text, sentiment, topic):
    r = LOCAL.classify("X", text)
    assert (r.sentiment, r.topic) == (sentiment, topic)


@pytest.mark.parametrize("text, lang", [("გამარჯობა", "ka"), ("Hello there", "en"), ("12345 !!", "other"),
                                        ("სერვისი OK", "ka")])
def test_language_detection_by_script(text, lang):
    assert detect_language(text) == lang


def test_local_classifier_is_deterministic():
    text = "Overpriced parts, I can find them cheaper elsewhere."
    assert LOCAL.classify("A", text) == LOCAL.classify("A", text)


# ---------------------------------------------------------------- output contract
@pytest.mark.parametrize("field, value", [("language", "fr"), ("sentiment", "angry"), ("topic", "weather"),
                                          ("confidence", 1.5)])
def test_contract_rejects_labels_outside_the_taxonomy(field, value):
    base = dict(feedback_id="X", language="en", sentiment="neutral", topic="other", confidence=0.5,
                method="gemini", model="m")
    with pytest.raises(InvalidClassification):
        validate(Classification(**{**base, field: value}))


def test_text_hash_matches_postgres_md5():
    assert text_hash("სერვისი") == hashlib.md5("სერვისი".encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- Gemini client behaviour (mocked)
class FakeModels:
    def __init__(self, behaviour):
        self.behaviour, self.calls = behaviour, 0

    def generate_content(self, model, contents, config):
        self.calls += 1
        result = self.behaviour(self.calls, contents)
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(parsed=None, text=result,
                               usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=5))


def fake_classifier(behaviour, batch_size=25):
    settings = load_settings({"AI_PROVIDER": "gemini", "AI_API_KEY": "k", "AI_BATCH_SIZE": str(batch_size)})
    client = SimpleNamespace(models=FakeModels(behaviour))
    return GeminiClassifier(settings, client=client), client.models


ITEMS = [("F1", "Great staff"), ("F2", "Too expensive"), ("F3", "Out of stock again")]


def test_valid_model_answers_are_used_and_invalid_or_missing_ones_fall_back():
    import json
    answer = json.dumps([
        {"id": "F1", "language": "en", "sentiment": "positive", "topic": "staff", "confidence": 0.93},
        {"id": "F2", "language": "en", "sentiment": "negative", "topic": "pricing", "confidence": 0.9},  # bad topic
        # F3 missing from the answer
    ])
    clf, _ = fake_classifier(lambda n, c: answer)
    out = {r.feedback_id: r for r in clf.classify_many(ITEMS)}
    assert out["F1"].method == "gemini" and out["F1"].topic == "staff" and out["F1"].confidence == 0.93
    assert out["F2"].method == "rule_based_fallback" and out["F2"].topic == "price"
    assert out["F3"].method == "rule_based_fallback" and out["F3"].topic == "availability"
    assert clf.stats["model_labels"] == 1 and clf.stats["fallback_labels"] == 2


def test_failed_request_falls_back_for_the_whole_batch():
    clf, models = fake_classifier(lambda n, c: ValueError("400 bad request"))
    out = clf.classify_many(ITEMS)
    assert all(r.method == "rule_based_fallback" for r in out)
    assert models.calls == 1 and clf.stats["failed_batches"] == 1      # non-retryable: no retry


def test_rate_limit_is_retried_with_backoff(monkeypatch):
    import json
    monkeypatch.setattr(gemini_module.time, "sleep", lambda s: None)
    rate_limited = type("RateLimit", (Exception,), {"code": 429})
    ok = json.dumps([{"id": fid, "language": "en", "sentiment": "neutral", "topic": "other", "confidence": 0.8}
                     for fid, _ in ITEMS])
    clf, models = fake_classifier(lambda n, c: rate_limited("slow down") if n < 3 else ok)
    out = clf.classify_many(ITEMS)
    assert models.calls == 3 and clf.stats["retries"] == 2
    assert all(r.method == "gemini" for r in out)


def test_items_are_sent_in_batches():
    import json

    def answer(n, contents):
        return json.dumps([{"id": i["id"], "language": "en", "sentiment": "neutral", "topic": "other",
                            "confidence": 0.7} for i in json.loads(contents)])
    clf, models = fake_classifier(answer, batch_size=2)
    clf.concurrency = 1
    assert len(clf.classify_many(ITEMS)) == 3 and models.calls == 2


def test_cost_budget_limits_items_sent_to_the_provider():
    pending = [(str(i), "t") for i in range(10)]
    to_model, to_local = split_budget(pending, external=True, budget=4)
    assert len(to_model) == 4 and len(to_local) == 6
    assert split_budget(pending, external=False, budget=4) == ([], pending)


# ---------------------------------------------------------------- evaluation
def test_evaluation_metrics():
    truth = pd.DataFrame({"feedback_id": ["1", "2", "3", "4"], "true_language": ["en"] * 4,
                          "true_sentiment": ["positive", "negative", "negative", "neutral"],
                          "true_topic": ["staff", "price", "price", "other"]})
    pred = pd.DataFrame({"feedback_id": ["1", "2", "3", "4"], "language": ["en"] * 4,
                         "sentiment": ["positive", "negative", "positive", "neutral"],
                         "topic": ["staff", "price", "price", "staff"]})
    m = evaluate(pred, truth)
    assert m["sentiment_accuracy"] == 0.75 and m["topic_accuracy"] == 0.75
    assert m["sentiment_and_topic_accuracy"] == 0.5
    assert m["topic_confusion"].loc["other", "staff"] == 1


def test_holdout_set_is_balanced_and_uses_valid_labels():
    h = load_holdout()
    assert len(h) == 40 and h.feedback_id.is_unique
    assert h.true_language.value_counts().to_dict() == {"en": 20, "ka": 20}
    assert set(h.true_sentiment) <= set(SENTIMENTS) and set(h.true_topic) <= set(TOPICS)
    assert set(h.true_language) <= set(LANGUAGES)


def test_local_classifier_accuracy_on_generated_feedback():
    from datagen.generate import generate_clean_datasets
    data = generate_clean_datasets(seed=11, scale=0.03)
    fb, labels = data["customer_feedback"], data["_feedback_labels"]
    pred = pd.DataFrame([c.as_row() for c in LOCAL.classify_many(list(zip(fb.feedback_id, fb.feedback_text)))])
    m = evaluate(pred, labels)
    assert m["sentiment_accuracy"] >= 0.95 and m["topic_accuracy"] >= 0.95 and m["language_accuracy"] == 1.0


# ---------------------------------------------------------------- insights (no database)
def test_template_insight_states_the_computed_facts():
    facts = {"scope": "branch", "scope_value": "AutoSphere Batumi", "period": "2026-Q3",
             "comparison_period": "2025-Q3", "feedback_count": 120, "negative_rate_pct": 41.5,
             "negative_rate_same_quarter_last_year_pct": 25.0, "avg_rating": 3.1,
             "top_complaint_topics": [{"topic": "waiting_time", "negatives": 30,
                                       "negatives_same_quarter_last_year": 8}],
             "anomalies": [{"branch": "AutoSphere Batumi", "topic": "waiting_time", "negatives": 30,
                            "baseline_avg_per_quarter": 9.0, "ratio_to_baseline": 3.33}],
             "maintenance_median_turnaround_hours": 7.1, "maintenance_median_turnaround_hours_last_year": 2.8}
    text = template_insight(facts)
    for fragment in ("41.5%", "+16.5 pp", "waiting_time", "3.33x", "7.1h", "Action:"):
        assert fragment in text


# ---------------------------------------------------------------- warehouse
@pytest.fixture(scope="module")
def cur(engine):
    conn = engine.raw_connection()
    with conn.cursor() as c:
        c.execute("SELECT count(*) FROM dw.feedback_classification")
        if c.fetchone()[0] == 0:
            conn.close()
            pytest.skip("no classifications - run scripts/run_pipeline.py first")
        yield c
    conn.rollback()
    conn.close()


def scalar(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


@pytest.mark.db
def test_every_feedback_in_the_warehouse_has_ai_labels_with_lineage(cur):
    assert scalar(cur, "SELECT count(*) FROM dw.fact_customer_feedback WHERE sentiment IS NULL "
                       "OR topic IS NULL OR classification_method IS NULL") == 0
    methods = scalar(cur, "SELECT array_agg(DISTINCT split_part(classification_method, ':', 1)) "
                          "FROM dw.fact_customer_feedback")
    assert set(methods) <= {"gemini", "rule_based", "rule_based_fallback"}


@pytest.mark.db
def test_ai_sentiment_largely_agrees_with_star_ratings(cur):
    agree = scalar(cur, "SELECT sum(feedback_count) FILTER (WHERE agreement = 'agree')::numeric / "
                        "sum(feedback_count) FROM analytics.v_rating_vs_sentiment")
    contradict = scalar(cur, "SELECT sum(feedback_count) FILTER (WHERE agreement = 'contradict')::numeric / "
                             "sum(feedback_count) FROM analytics.v_rating_vs_sentiment")
    assert agree > 0.75 and contradict < 0.08


@pytest.mark.db
def test_anomaly_detection_flags_batumi_waiting_time_in_2026(cur):
    if scalar(cur, "SELECT count(*) FROM analytics.v_feedback WHERE branch_name = 'AutoSphere Batumi'") == 0:
        pytest.skip("dataset without the Batumi branch")
    assert scalar(cur, "SELECT count(*) FROM analytics.v_feedback_anomalies WHERE is_anomaly "
                       "AND branch_name = 'AutoSphere Batumi' AND topic = 'waiting_time' AND year = 2026") >= 1


@pytest.mark.db
def test_insights_exist_for_company_and_every_branch(cur):
    assert scalar(cur, "SELECT count(*) FROM analytics.v_ai_insights_latest WHERE scope = 'company'") == 1
    assert scalar(cur, "SELECT count(*) FROM analytics.v_ai_insights_latest WHERE scope = 'branch'") == \
        scalar(cur, "SELECT count(DISTINCT branch_name) FROM analytics.v_feedback")
