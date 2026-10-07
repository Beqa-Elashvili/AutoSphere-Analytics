"""Gemini-based feedback classifier with structured output, validation and fallback.

Design:
  * batches of `ai_batch_size` feedback items per request, `ai_concurrency` requests in parallel
  * structured JSON output constrained to the label taxonomy (response_schema + enums), temperature 0
  * minimal "thinking": classification needs no long reasoning (about 3x faster, fewer tokens)
  * retries with exponential backoff on rate limits (429) and server errors (5xx)
  * every returned item is validated; missing or invalid items fall back to the local
    rule-based classifier and are marked 'rule_based_fallback' (never silently guessed)
"""
from __future__ import annotations

import json
import random
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel

from ai.classification.rule_based import RuleBasedClassifier
from ai.schema import GUIDELINES, Classification, InvalidClassification, validate
from common.config import Settings
from common.logging_config import get_logger

log = get_logger("ai.gemini")

SYSTEM_PROMPT = f"""\
You classify customer feedback for an automotive dealer and service network in Georgia
(vehicle sales, spare parts, service centres). Feedback is written in Georgian or English.

For every input item return exactly one object with the same id and:
- language: ka | en | other
- sentiment: positive | neutral | negative
- topic: service_quality | waiting_time | price | staff | product_quality | availability | complaint | other
- confidence: your probability (0..1) that BOTH sentiment and topic are correct

{GUIDELINES}
Examples:
"სერვისი კარგი იყო, მაგრამ ძალიან დიდხანს მომიწია ლოდინი." -> ka, negative, waiting_time
"Waiting two weeks for a part that should be in stock." -> en, negative, availability
"Prices are average for the market." -> en, neutral, price
"Do you work on Sundays?" -> en, neutral, other
"""


class FeedbackLabel(BaseModel):
    id: str
    language: Literal["ka", "en", "other"]
    sentiment: Literal["positive", "neutral", "negative"]
    topic: Literal["service_quality", "waiting_time", "price", "staff", "product_quality",
                   "availability", "complaint", "other"]
    confidence: float


def _status_code(exc: Exception) -> int | None:
    return getattr(exc, "code", None) or getattr(exc, "status_code", None)


class GeminiClassifier:
    method = "gemini"

    def __init__(self, settings: Settings, client=None, fallback: RuleBasedClassifier | None = None,
                 max_retries: int = 5):
        self.model = settings.ai_model
        self.batch_size = settings.ai_batch_size
        self.concurrency = settings.ai_concurrency
        self.max_retries = max_retries
        self.fallback = fallback or RuleBasedClassifier()
        self.stats: Counter = Counter()
        if client is None:
            from google import genai
            client = genai.Client(api_key=settings.ai_api_key)
        self.client = client

    # -- one API call --------------------------------------------------------------
    def _config(self):
        from google.genai import types
        return types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=list[FeedbackLabel],
            temperature=0,
            thinking_config=types.ThinkingConfig(thinking_level="minimal"),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def _request(self, batch: list[tuple[str, str]]) -> list[dict]:
        payload = json.dumps([{"id": fid, "text": text} for fid, text in batch], ensure_ascii=False)
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model, contents=payload, config=self._config())
                usage = getattr(response, "usage_metadata", None)
                if usage is not None:
                    self.stats["input_tokens"] += usage.prompt_token_count or 0
                    self.stats["output_tokens"] += usage.candidates_token_count or 0
                self.stats["requests"] += 1
                parsed = getattr(response, "parsed", None)
                if parsed is not None:
                    return [p.model_dump() if hasattr(p, "model_dump") else dict(p) for p in parsed]
                return json.loads(response.text)
            except Exception as exc:  # noqa: BLE001 - decide below whether it is retryable
                code = _status_code(exc)
                retryable = code == 429 or (isinstance(code, int) and code >= 500)
                if not retryable or attempt == self.max_retries:
                    raise
                delay = min(60.0, 2 ** attempt + random.uniform(0, 1))
                self.stats["retries"] += 1
                log.warning("Gemini HTTP %s, retry %d/%d in %.0fs", code, attempt, self.max_retries, delay)
                time.sleep(delay)
        raise RuntimeError("unreachable")

    # -- one batch, validated --------------------------------------------------------
    def _classify_batch(self, batch: list[tuple[str, str]]) -> list[Classification]:
        try:
            answers = {str(a.get("id")): a for a in self._request(batch)}
        except Exception as exc:  # noqa: BLE001 - whole batch falls back, pipeline continues
            log.error("Gemini batch of %d failed (%s) - using rule-based fallback", len(batch), exc)
            self.stats["failed_batches"] += 1
            answers = {}
        out = []
        for fid, text in batch:
            a = answers.get(fid)
            try:
                if a is None:
                    raise InvalidClassification(f"{fid}: missing in model response")
                out.append(validate(Classification(
                    fid, a["language"], a["sentiment"], a["topic"],
                    round(float(a["confidence"]), 3), self.method, self.model)))
                self.stats["model_labels"] += 1
            except (InvalidClassification, KeyError, TypeError, ValueError) as exc:
                self.stats["fallback_labels"] += 1
                log.debug("Fallback for %s: %s", fid, exc)
                out.append(self.fallback.classify(fid, text, method="rule_based_fallback"))
        return out

    def classify_many(self, items: list[tuple[str, str]]) -> list[Classification]:
        batches = [items[i:i + self.batch_size] for i in range(0, len(items), self.batch_size)]
        results: list[Classification] = []
        done = 0
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            for batch_result in pool.map(self._classify_batch, batches):
                results.extend(batch_result)
                done += 1
                if done % 20 == 0 or done == len(batches):
                    log.info("Gemini: %d/%d batches, %d items", done, len(batches), len(results))
        return results

    def classify(self, feedback_id: str, text: str) -> Classification:
        return self.classify_many([(feedback_id, text)])[0]
