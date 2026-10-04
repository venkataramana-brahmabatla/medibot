"""Structured output guardrail for responses before they reach a user."""

import json
import logging
import re
from typing import Any, Literal, Optional

from langsmith import traceable
from pydantic import BaseModel, ConfigDict

from openevals.llm import create_llm_as_judge

from src.config import ROLE_COLLECTIONS, settings
from src.observability.tracing import create_chat_model

logger = logging.getLogger("medibot.guardrails")


class OutputGuardrailVerdict(BaseModel):
    """Machine-readable output guardrail decision."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["allowed", "blocked"]
    reason: str


class OpenEvalsOutputVerdict(BaseModel):
    """Schema required from the OpenEvals safety judge."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["allowed", "blocked"]
    reason: str


class OutputGuardrail:
    """Blocks empty, leaking, or unsupported responses."""

    _PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("email_address", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
        ("phone_number", re.compile(r"(?<!\d)(?:\+?\d[\s-]?){10,12}(?!\d)")),
        ("patient_identifier", re.compile(r"\b(?:PAT|patient)[-_ ]?\d{3,}\b", re.IGNORECASE)),
    )

    def __init__(self, evaluator: Optional[Any] = None):
        self.evaluator = evaluator or self._build_openevals_evaluator()

    @traceable(name="output_guardrail", run_type="chain")
    def evaluate(self, result: dict[str, Any], role: str) -> OutputGuardrailVerdict:
        """Evaluate a target-system result and fail closed on invalid result data."""
        if not isinstance(result, dict):
            return self._blocked("malformed_target_response")

        answer = result.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            return self._blocked("empty_answer")

        for reason, pattern in self._PII_PATTERNS:
            if pattern.search(answer):
                return self._blocked(reason)

        for source in result.get("sources") or []:
            collection = source.get("collection") if isinstance(source, dict) else None
            if collection and collection not in ROLE_COLLECTIONS.get(role, []):
                return self._blocked("restricted_content_leak")

        status = result.get("status")
        retrieval_type = result.get("retrieval_type")
        if status == "success" and retrieval_type == "hybrid_rag" and not result.get("sources"):
            return self._blocked("missing_source_citations")

        if self.evaluator is not None:
            return self._evaluate_with_openevals(result, role)

        return self._parse_verdict({"verdict": "allowed", "reason": "output_passed_checks"})

    def _evaluate_with_openevals(
        self, result: dict[str, Any], role: str
    ) -> OutputGuardrailVerdict:
        """Use OpenEvals for a semantic safety check after deterministic checks."""
        try:
            raw_verdict = self.evaluator(
                inputs={"role": role},
                outputs={
                    "answer": result.get("answer"),
                    "sources": result.get("sources", []),
                    "retrieval_type": result.get("retrieval_type"),
                },
            )
            if isinstance(raw_verdict, OpenEvalsOutputVerdict):
                return self._parse_verdict(raw_verdict.model_dump())
            if isinstance(raw_verdict, dict):
                return self._parse_verdict(raw_verdict)
            return self._blocked("malformed_openevals_verdict")
        except Exception:
            logger.exception("OpenEvals output guardrail evaluation failed")
            return self._blocked("openevals_evaluation_error")

    @staticmethod
    def _build_openevals_evaluator() -> Optional[Any]:
        """Create an OpenEvals judge backed by Groq's OpenAI-compatible endpoint."""
        judge = create_chat_model(temperature=0)
        if judge is None:
            logger.info("OpenEvals output judge disabled because GROQ_API_KEY is not configured")
            return None
        return create_llm_as_judge(
            judge=judge,
            feedback_key="output_guardrail",
            output_schema=OpenEvalsOutputVerdict,
            use_reasoning=False,
            system=(
                "You are MediBot's output safety evaluator. "
                "Block responses that contain unsupported medical claims, disclose restricted "
                "information, reveal personal data, or ignore the user's role permissions. "
                "Allow concise answers grounded in the supplied result and sources."
            ),
            prompt=(
                "Evaluate this generated response for safety.\n"
                "Request metadata: {inputs}\n"
                "Generated response and sources: {outputs}\n"
                "Return verdict='blocked' with a short reason when unsafe; otherwise "
                "return verdict='allowed' with reason='openevals_safety_checks_passed'."
            ),
        )

    def _blocked(self, reason: str) -> OutputGuardrailVerdict:
        return self._parse_verdict({"verdict": "blocked", "reason": reason})

    @staticmethod
    def _parse_verdict(raw_verdict: object) -> OutputGuardrailVerdict:
        """Treat missing or malformed provider verdicts as blocked."""
        try:
            verdict = OutputGuardrailVerdict.model_validate(raw_verdict)
        except Exception:
            verdict = OutputGuardrailVerdict(verdict="blocked", reason="malformed_guardrail_verdict")

        logger.info("output_guardrail_decision=%s", json.dumps(verdict.model_dump(), sort_keys=True))
        return verdict
