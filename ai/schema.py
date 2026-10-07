"""Label taxonomy and the structured output contract shared by every classifier."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

LANGUAGES = ("ka", "en", "other")
SENTIMENTS = ("positive", "neutral", "negative")
TOPICS = ("service_quality", "waiting_time", "price", "staff", "product_quality",
          "availability", "complaint", "other")

# Shared labelling guideline (also sent to the LLM): one label set, one meaning.
GUIDELINES = """\
Labelling rules:
- topic = the main subject of the feedback; if there is a problem, the topic is the problem.
- sentiment = overall tone. Mixed feedback that contains a complaint is 'negative'
  (e.g. "service was good, but the wait was very long" -> negative, waiting_time).
- waiting_time: speed, delays, how long the customer waited or the car took.
- availability: products or parts in stock / out of stock / had to be ordered.
- price: prices, bills, estimates, discounts, value for money.
- staff: behaviour, politeness, communication or helpfulness of employees.
- product_quality: quality of a sold product (tires, batteries, parts, accessories).
- service_quality: quality of repair or maintenance work.
- complaint: formal complaints, refund demands, damage claims, "never coming back".
- other: questions, requests and generic thanks without a specific subject.
- language: 'ka' for Georgian, 'en' for English, 'other' otherwise.
"""


@dataclass(frozen=True)
class Classification:
    feedback_id: str
    language: str
    sentiment: str
    topic: str
    confidence: float
    method: str            # gemini | rule_based | rule_based_fallback
    model: str             # e.g. gemini-3.5-flash | rules-v1

    def as_row(self) -> dict:
        return asdict(self)


class InvalidClassification(ValueError):
    """A model returned something outside the label contract."""


def validate(c: Classification) -> Classification:
    """Enforce the output contract: known labels and a confidence in [0, 1]."""
    if c.language not in LANGUAGES:
        raise InvalidClassification(f"{c.feedback_id}: unknown language '{c.language}'")
    if c.sentiment not in SENTIMENTS:
        raise InvalidClassification(f"{c.feedback_id}: unknown sentiment '{c.sentiment}'")
    if c.topic not in TOPICS:
        raise InvalidClassification(f"{c.feedback_id}: unknown topic '{c.topic}'")
    if not 0.0 <= float(c.confidence) <= 1.0:
        raise InvalidClassification(f"{c.feedback_id}: confidence {c.confidence} outside [0, 1]")
    return c


def text_hash(text: str) -> str:
    """Same as PostgreSQL md5(text): detects edited feedback that needs re-classification."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()
