"""
LLM-based probability forecaster.

Prompts a Claude model with a prediction-market question and extracts a
probability in [0, 1] from its response using structured output.

The prompt follows a chain-of-thought → probability format:
  1. Brief reasoning about the question
  2. Final answer: a single float in [0, 1]

Usage
-----
    from models.llm_forecaster import LLMForecaster
    forecaster = LLMForecaster(model="claude-sonnet-4-6")
    prob = forecaster.forecast("Will the Fed cut rates in June 2025?")
    # → 0.72
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import (
    ANTHROPIC_API_KEY, DEFAULT_MODEL, MAX_TOKENS,
    TEMPERATURE, N_RETRIES, RETRY_DELAY_SEC,
)

try:
    import anthropic
except ImportError:
    print("Install: uv pip install --system anthropic", file=sys.stderr)
    raise


SYSTEM_PROMPT = """\
You are an expert forecaster. Your job is to estimate the probability that a
prediction-market question resolves YES (i.e., the described event happens).

Instructions:
1. Think step-by-step about the question: relevant base rates, recent evidence,
   uncertainty sources.
2. On the FINAL line of your response, output ONLY:
   PROBABILITY: <number between 0.0 and 1.0>

Be calibrated — do not round to 0 or 1 unless you are certain.
"""

USER_TEMPLATE = """\
Question: {question}
Resolution date: {resolution_date}

What is the probability this resolves YES?
"""


def _extract_probability(text: str) -> float | None:
    """Pull the float from 'PROBABILITY: 0.73' in model output."""
    # Search for the marker line
    m = re.search(r"PROBABILITY\s*:\s*([0-9]*\.?[0-9]+)", text, re.IGNORECASE)
    if m:
        val = float(m.group(1))
        return max(0.0, min(1.0, val))
    # Fallback: last standalone float on its own line
    lines = text.strip().splitlines()
    for line in reversed(lines):
        m2 = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*", line)
        if m2:
            val = float(m2.group(1))
            if 0.0 <= val <= 1.0:
                return val
    return None


class LLMForecaster:
    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None):
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key or ANTHROPIC_API_KEY or None)

    def forecast(
        self,
        question: str,
        resolution_date: str = "",
        context: str = "",
    ) -> dict:
        """
        Returns a dict:
          {
            "probability": float,    # in [0, 1], or None on failure
            "reasoning":   str,      # full model response
            "model":       str,
            "raw_prompt":  str,
          }
        """
        user_msg = USER_TEMPLATE.format(
            question=question,
            resolution_date=resolution_date or "unspecified",
        )
        if context:
            user_msg += f"\nAdditional context:\n{context}\n"

        last_error = None
        for attempt in range(N_RETRIES):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=MAX_TOKENS,
                    temperature=TEMPERATURE,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_msg}],
                )
                text = response.content[0].text
                prob = _extract_probability(text)
                return {
                    "probability": prob,
                    "reasoning":   text,
                    "model":       self.model,
                    "raw_prompt":  user_msg,
                }
            except Exception as exc:
                last_error = exc
                if attempt < N_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SEC * (2 ** attempt))

        return {
            "probability": None,
            "reasoning":   f"ERROR: {last_error}",
            "model":       self.model,
            "raw_prompt":  user_msg,
        }

    def batch_forecast(self, questions: list[dict], verbose: bool = True) -> list[dict]:
        """
        Forecast a list of question dicts (each with keys: question, resolution_date).
        Returns each dict enriched with llm_probability and llm_reasoning.
        """
        results = []
        for i, q in enumerate(questions):
            if verbose and i % 10 == 0:
                print(f"  [{i+1}/{len(questions)}] {q['question'][:80]} …")
            out = self.forecast(
                question=q["question"],
                resolution_date=q.get("resolution_date", ""),
            )
            result = {**q, "llm_probability": out["probability"], "llm_reasoning": out["reasoning"]}
            results.append(result)
        return results
