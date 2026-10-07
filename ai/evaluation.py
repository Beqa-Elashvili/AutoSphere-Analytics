"""Measure classifier quality against ground-truth labels.

Two evaluation sets:
  * generated : the synthetic feedback with the generator's labels (template phrasing;
                optimistic for the rule-based classifier, whose lexicon was built on it)
  * holdout   : 40 hand-written Georgian/English items with NEW phrasing (ai/eval/),
                the honest test of generalisation
"""
from __future__ import annotations

import pandas as pd

from common.config import PROJECT_ROOT

HOLDOUT_PATH = PROJECT_ROOT / "ai" / "eval" / "holdout_feedback.csv"
GENERATED_LABELS = PROJECT_ROOT / "data" / "evaluation" / "feedback_labels.csv"
GENERATED_FEEDBACK = PROJECT_ROOT / "data" / "raw" / "customer_feedback.csv"
FIELDS = ("language", "sentiment", "topic")


def load_holdout() -> pd.DataFrame:
    return pd.read_csv(HOLDOUT_PATH, dtype=str)


def load_generated(sample: int | None = None, seed: int = 7) -> pd.DataFrame:
    fb = pd.read_csv(GENERATED_FEEDBACK, dtype=str, keep_default_na=False).drop_duplicates("feedback_id")
    fb = fb[fb.feedback_text.str.strip() != ""]
    df = fb[["feedback_id", "feedback_text"]].merge(pd.read_csv(GENERATED_LABELS, dtype=str), on="feedback_id")
    if sample and sample < len(df):
        df = df.sample(sample, random_state=seed)
    return df.reset_index(drop=True)


def per_class(truth: pd.Series, pred: pd.Series) -> pd.DataFrame:
    rows = []
    for label in sorted(set(truth) | set(pred)):
        tp = int(((truth == label) & (pred == label)).sum())
        precision = tp / max(int((pred == label).sum()), 1)
        recall = tp / max(int((truth == label).sum()), 1)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        rows.append({"label": label, "support": int((truth == label).sum()),
                     "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)})
    return pd.DataFrame(rows)


def evaluate(predictions: pd.DataFrame, truth: pd.DataFrame) -> dict:
    """predictions: feedback_id + language/sentiment/topic (+confidence);
    truth: feedback_id + true_language/true_sentiment/true_topic."""
    m = truth.merge(predictions, on="feedback_id", how="inner")
    out = {"items": len(m)}
    for f in FIELDS:
        out[f"{f}_accuracy"] = round(float((m[f] == m[f"true_{f}"]).mean()), 4)
    both = (m.sentiment == m.true_sentiment) & (m.topic == m.true_topic)
    out["sentiment_and_topic_accuracy"] = round(float(both.mean()), 4)
    out["by_language"] = {lang: round(float(both[m.true_language == lang].mean()), 4)
                          for lang in sorted(m.true_language.unique())}
    for f in ("sentiment", "topic"):
        pc = per_class(m[f"true_{f}"], m[f])
        out[f"{f}_macro_f1"] = round(float(pc.f1.mean()), 4)
        out[f"{f}_per_class"] = pc
        out[f"{f}_confusion"] = pd.crosstab(m[f"true_{f}"], m[f], rownames=["true"], colnames=["predicted"])
    if "confidence" in m:
        m["correct"] = both
        out["calibration"] = (m.assign(band=pd.cut(m.confidence.astype(float), [0, .6, .8, .9, 1.0],
                                                   include_lowest=True))
                              .groupby("band", observed=True).correct.agg(["count", "mean"]).round(3))
    out["errors"] = m[~both][["feedback_id", "feedback_text", "true_sentiment", "true_topic", "sentiment", "topic"]] \
        if "feedback_text" in m else m[~both]
    return out


def to_markdown(results: dict[str, dict], title: str) -> str:
    lines = [f"# {title}", ""]
    lines += ["| Dataset | Items | Language | Sentiment | Topic | Sentiment + topic | Sentiment macro-F1 | Topic macro-F1 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, r in results.items():
        lines.append(f"| {name} | {r['items']} | {r['language_accuracy']:.1%} | {r['sentiment_accuracy']:.1%} | "
                     f"{r['topic_accuracy']:.1%} | {r['sentiment_and_topic_accuracy']:.1%} | "
                     f"{r['sentiment_macro_f1']:.3f} | {r['topic_macro_f1']:.3f} |")
    for name, r in results.items():
        lines += ["", f"## {name}", "", f"Accuracy (sentiment + topic) by language: {r['by_language']}", "",
                  "### Topic per class", "", r["topic_per_class"].to_markdown(index=False), "",
                  "### Topic confusion matrix", "", r["topic_confusion"].to_markdown(), ""]
        if "calibration" in r:
            lines += ["### Confidence calibration (share correct per confidence band)", "",
                      r["calibration"].to_markdown(), ""]
        errors = r["errors"].head(15)
        if not errors.empty:
            lines += ["### Sample errors", "", errors.to_markdown(index=False), ""]
    return "\n".join(lines)
