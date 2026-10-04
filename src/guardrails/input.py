"""
Structured input guardrail for requests entering the MediBot pipeline.

The guardrail runs before routing or retrieval. It deliberately fails closed:
only an explicit ``allowed`` verdict from the local checks is treated as allowed.
"""

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict
from langsmith import traceable

logger = logging.getLogger("medibot.guardrails")


class InputGuardrailVerdict(BaseModel):
    """Machine-readable input guardrail decision."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["allowed", "blocked"]
    reason: str


class InputGuardrail:
    """Blocks prompt injection, RBAC bypass attempts, and unrelated abuse."""

    _BLOCK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        (
            "prompt_injection",
            re.compile(
                r"\b(ignore|disregard|forget|override|bypass)\b.{0,80}"
                r"\b(instructions?|rules?|system prompt|safety|previous messages?)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "rbac_override_attempt",
            re.compile(
                r"\b(bypass|circumvent|override)\b.{0,80}"
                r"\b(access|permissions?|rbac|restrictions?|security)\b|"
                r"\b(pretend|act)\b.{0,30}\b(admin|doctor|billing)\b|"
                r"\b(show|reveal|give)\b.{0,80}\b(restricted|private|confidential)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "off_topic_request",
            re.compile(
                r"\b(?:what(?:'s| is) the weather|weather forecast|weather today|"
                r"sports? scores?|football scores?|cricket scores?|stock market|"
                r"celebrity gossip|politics?|lottery numbers?|recipe for|"
                r"movie review|tell me a joke|latest news|news headlines)\b",
                re.IGNORECASE,
            ),
        ),
    )

    @traceable(name="input_guardrail", run_type="chain")
    def evaluate(self, question: str) -> InputGuardrailVerdict:
        """Return a structured decision from deterministic input checks."""
        if not isinstance(question, str) or not question.strip():
            return self._blocked("empty_or_invalid_question")

        for reason, pattern in self._BLOCK_PATTERNS:
            if pattern.search(question):
                return self._blocked(reason)

        return self._parse_verdict({"verdict": "allowed", "reason": "input_passed_checks"})

    def _blocked(self, reason: str) -> InputGuardrailVerdict:
        return self._parse_verdict({"verdict": "blocked", "reason": reason})

    @staticmethod
    def _parse_verdict(raw_verdict: object) -> InputGuardrailVerdict:
        """Validate structured decision data, blocking missing or malformed values."""
        try:
            verdict = InputGuardrailVerdict.model_validate(raw_verdict)
        except Exception:
            verdict = InputGuardrailVerdict(verdict="blocked", reason="malformed_guardrail_verdict")

        logger.info("input_guardrail_decision=%s", json.dumps(verdict.model_dump(), sort_keys=True))
        return verdict
