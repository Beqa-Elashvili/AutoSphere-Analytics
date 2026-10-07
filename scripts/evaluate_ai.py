"""Evaluate the feedback classifiers against ground truth.

Usage:
    python scripts/evaluate_ai.py                        # configured provider, holdout + generated sample
    python scripts/evaluate_ai.py --provider local       # rule-based classifier
    python scripts/evaluate_ai.py --provider gemini --sample 300
    python scripts/evaluate_ai.py --stored               # labels currently stored in the warehouse

Writes reports/ai_evaluation_<provider>.md (per-class metrics, confusion matrix, errors).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from ai.evaluation import evaluate, load_generated, load_holdout, to_markdown  # noqa: E402
from ai.pipeline import get_classifier  # noqa: E402
from common.config import PROJECT_ROOT, load_settings  # noqa: E402


def classify(df: pd.DataFrame, classifier) -> pd.DataFrame:
    items = list(zip(df.feedback_id, df.feedback_text))
    return pd.DataFrame([c.as_row() for c in classifier.classify_many(items)])


def stored_labels() -> pd.DataFrame:
    from common.db import get_engine
    conn = get_engine().raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT feedback_id, language, sentiment, topic, confidence, method FROM dw.feedback_classification")
            return pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", choices=["local", "gemini"], help="default: AI_PROVIDER from .env")
    parser.add_argument("--sample", type=int, default=None,
                        help="generated items to evaluate (default: all for local, 300 for gemini)")
    parser.add_argument("--stored", action="store_true", help="evaluate labels stored in dw.feedback_classification")
    args = parser.parse_args()

    results = {}
    if args.stored:
        pred = stored_labels()
        pred["confidence"] = pred.confidence.astype(float)
        truth = load_generated()
        label = "stored"
        methods = pred.method.value_counts().to_dict()
        results[f"warehouse labels {methods}"] = evaluate(pred, truth)
    else:
        settings = load_settings()
        if args.provider:
            settings = settings.with_provider(args.provider)
        label = "gemini" if settings.ai_mode == "external" else "local"
        sample = args.sample or (300 if label == "gemini" else None)
        classifier = get_classifier(settings)
        holdout, generated = load_holdout(), load_generated(sample)
        results["holdout (new phrasing, 40 items)"] = evaluate(classify(holdout, classifier), holdout)
        results[f"generated ({len(generated)} items)"] = evaluate(classify(generated, classifier), generated)

    out = PROJECT_ROOT / "reports" / f"ai_evaluation_{label}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(to_markdown(results, f"AI feedback classification - evaluation ({label})"), encoding="utf-8")

    print(f"{'dataset':45s} {'items':>6s} {'lang':>7s} {'sent':>7s} {'topic':>7s} {'both':>7s}")
    for name, r in results.items():
        print(f"{name:45s} {r['items']:6d} {r['language_accuracy']:7.1%} {r['sentiment_accuracy']:7.1%} "
              f"{r['topic_accuracy']:7.1%} {r['sentiment_and_topic_accuracy']:7.1%}")
    print(f"\nFull report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
