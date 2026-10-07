"""Deterministic, offline feedback classifier (the fallback when no AI provider is configured).

How it works:
  1. language  : share of Georgian vs Latin letters
  2. sentiment : bilingual lexicon; phrases are matched (and removed) before words;
                 with "but / მაგრამ" the clause AFTER the contrast decides;
                 mixed praise + complaint counts as negative (labelling guideline)
  3. topic     : keyword hits per topic; contrast clause first; ties -> PRIORITY order
  4. confidence: grows with the number and decisiveness of matched cues

Fast (~50k texts/s), free, reproducible: used for tests, CI, local development and as
the per-item fallback when the external model returns an invalid answer.
"""
from __future__ import annotations

import re

from ai.classification.topics import PRIORITY, TOPIC_KEYWORDS
from ai.schema import Classification, validate
from ai.sentiment.lexicon import (
    CONTRAST_MARKERS, NEGATIVE_PHRASES, NEGATIVE_WORDS, NEUTRAL_PHRASES, POSITIVE_PHRASES, POSITIVE_WORDS,
)

GEORGIAN = re.compile(r"[Ⴀ-ჿ]")
LATIN = re.compile(r"[A-Za-z]")
MODEL_VERSION = "rules-v1"


def detect_language(text: str) -> str:
    ka, en = len(GEORGIAN.findall(text)), len(LATIN.findall(text))
    if ka == 0 and en == 0:
        return "other"
    return "ka" if ka >= en else "en"


def _pattern(term: str) -> re.Pattern:
    """English: match at a word start (prefix, so 'wait' matches 'waiting'); very short
    terms must also end at a word boundary ('ok' must not match 'took').
    Georgian: plain substring (stems inside agglutinated words)."""
    if GEORGIAN.search(term):
        return re.compile(re.escape(term))
    tail = r"(?![a-z])" if len(term) <= 3 else ""
    return re.compile(r"(?<![a-z])" + re.escape(term) + tail)


def _compile(terms):
    return [(t, _pattern(t)) for t in terms]


_NEG_PHRASES = _compile(NEGATIVE_PHRASES)
_POS_PHRASES = _compile(POSITIVE_PHRASES)
_NEU_PHRASES = _compile(NEUTRAL_PHRASES)
_POS_WORDS = _compile(POSITIVE_WORDS)
_NEG_WORDS = _compile(NEGATIVE_WORDS)
_TOPICS = {topic: _compile(words) for topic, words in TOPIC_KEYWORDS.items()}


def _normalize(text: str) -> str:
    text = text.lower().replace("’", "'")
    text = re.sub(r"[!?.;:]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return f" {text} "


def _split_contrast(text: str) -> tuple[str, str | None]:
    for marker in CONTRAST_MARKERS:
        idx = text.find(marker)
        if idx >= 0:
            return text[:idx], text[idx + len(marker):]
    return text, None


def _sentiment_cues(segment: str) -> tuple[int, int, int]:
    """Count (positive, negative, neutral) cues. Matched phrases are removed first."""
    pos = neg = neu = 0
    for group, kind in ((_NEG_PHRASES, "neg"), (_POS_PHRASES, "pos"), (_NEU_PHRASES, "neu")):
        for _, pat in group:
            hits = len(pat.findall(segment))
            if hits:
                segment = pat.sub(" ", segment)
                if kind == "neg":
                    neg += hits
                elif kind == "pos":
                    pos += hits
                else:
                    neu += hits
    pos += sum(len(p.findall(segment)) for _, p in _POS_WORDS)
    neg += sum(len(p.findall(segment)) for _, p in _NEG_WORDS)
    return pos, neg, neu


def _decide_sentiment(pos: int, neg: int, neu: int) -> tuple[str, float]:
    if neu and abs(pos - neg) <= 1 and neg < 2:
        return "neutral", 0.6 + 0.05 * min(neu, 2)
    if neg and neg >= pos:
        return "negative", min(0.95, 0.6 + 0.1 * neg)
    if pos > neg:
        return "positive", min(0.95, 0.6 + 0.1 * (pos - neg))
    return "neutral", 0.45


def _topic_hits(segment: str) -> dict[str, int]:
    return {topic: sum(len(p.findall(segment)) for _, p in pats) for topic, pats in _TOPICS.items()}


def _decide_topic(hits: dict[str, int]) -> tuple[str, int, bool]:
    best = max(hits.values())
    if best == 0:
        return "other", 0, False
    leaders = [t for t in PRIORITY if hits[t] == best]
    return leaders[0], best, len(leaders) > 1


class RuleBasedClassifier:
    method = "rule_based"
    model = MODEL_VERSION

    def classify(self, feedback_id: str, text: str, method: str | None = None) -> Classification:
        language = detect_language(text)
        norm = _normalize(text)
        head, tail = _split_contrast(norm)

        # Sentiment: the clause after a contrast marker decides when it carries any cue.
        if tail is not None and any(_sentiment_cues(tail)):
            sentiment, s_conf = _decide_sentiment(*_sentiment_cues(tail))
        else:
            sentiment, s_conf = _decide_sentiment(*_sentiment_cues(norm))
        if text.strip().endswith("?") and sentiment == "positive":
            sentiment, s_conf = "neutral", 0.5           # questions are requests, not praise

        # Topic: the contrast clause first (it usually names the problem).
        tail_hits = _topic_hits(tail) if tail is not None else None
        if tail_hits and max(tail_hits.values()) > 0:
            topic, n, tie = _decide_topic(tail_hits)
        else:
            topic, n, tie = _decide_topic(_topic_hits(norm))
        t_conf = 0.35 if n == 0 else min(0.95, 0.55 + 0.15 * min(n, 3) - (0.15 if tie else 0))

        confidence = round(min(s_conf, t_conf) * 0.5 + (s_conf + t_conf) / 4, 3)
        return validate(Classification(feedback_id, language, sentiment, topic, confidence,
                                       method or self.method, self.model))

    def classify_many(self, items: list[tuple[str, str]]) -> list[Classification]:
        return [self.classify(fid, text) for fid, text in items]
