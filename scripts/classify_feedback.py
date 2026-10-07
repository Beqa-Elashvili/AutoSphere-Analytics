"""Classify feedback text from the command line (Georgian or English).

Usage:
    python scripts/classify_feedback.py                                   # built-in examples
    python scripts/classify_feedback.py "სერვისი კარგი იყო, მაგრამ ძალიან დიდხანს მომიწია ლოდინი."
    python scripts/classify_feedback.py "Too expensive" "Great staff" --provider gemini
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from ai.pipeline import get_classifier  # noqa: E402
from common.config import load_settings  # noqa: E402

EXAMPLES = [
    "სერვისი კარგი იყო, მაგრამ ძალიან დიდხანს მომიწია ლოდინი.",
    "The staff was very friendly and explained everything.",
    "Waiting two weeks for a part that should be in stock.",
    "ფასები ძალიან გაიზარდა, ზედმეტად ძვირია.",
    "Do you work on Sundays?",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("texts", nargs="*", help="feedback text(s); default: built-in examples")
    parser.add_argument("--provider", choices=["local", "gemini"], help="default: AI_PROVIDER from .env")
    args = parser.parse_args()

    settings = load_settings()
    if args.provider:
        settings = settings.with_provider(args.provider)
    classifier = get_classifier(settings)
    texts = args.texts or EXAMPLES
    results = classifier.classify_many([(f"T{i + 1}", t) for i, t in enumerate(texts)])

    print(f"Mode: {settings.ai_mode} ({settings.ai_model if settings.ai_mode == 'external' else 'rules-v1'})\n")
    for text, r in zip(texts, results):
        print(f"{text}\n  -> language={r.language}  sentiment={r.sentiment}  topic={r.topic}  "
              f"confidence={r.confidence:.2f}  method={r.method}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
