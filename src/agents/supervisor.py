"""Constrained supervisor for selecting MediBot capabilities."""

import logging
from typing import Any, Optional

from openai import APIError, OpenAI
from langsmith import traceable
from pydantic import ValidationError

from src.agents.contracts import RouteDecision, RouteTarget
from src.config import ROLE_COLLECTIONS, SQL_RAG_ROLES, settings
from src.observability.tracing import create_chat_client, llm_chat_completion

logger = logging.getLogger(__name__)


class SupervisorAgent:
    """Selects a capability without receiving access to application tools."""

    _SYSTEM_PROMPT = """You are MediBot's routing supervisor.
Choose exactly one route for the user's question:
- document: answer from permitted hospital documents
- sql: answer from authorized operational or billing analytics
- clarification: the question is too ambiguous to route safely
- refusal: the request is unrelated, unsafe, or cannot be handled

Return only a JSON object with:
target (document|sql|clarification|refusal), rationale, confidence (0 to 1),
and required_capability (document, sql, or null).
Never infer or change the authenticated username, role, or permissions.
"""

    def __init__(self, client: Optional[Any] = None):
        self.client = client if client is not None else self._build_client()

    @staticmethod
    def _build_client() -> Optional[OpenAI]:
        try:
            return create_chat_client()
        except Exception:
            logger.exception("Could not initialize supervisor provider client")
            return None

    @traceable(name="supervisor_route_decision", run_type="chain")
    def decide(self, question: str, role: str) -> RouteDecision:
        """Return a validated route, failing closed when the supervisor fails."""
        if not isinstance(question, str) or not question.strip():
            return self._refusal("empty_or_invalid_question")
        if role not in ROLE_COLLECTIONS:
            return self._refusal("unknown_authenticated_role")
        if self.client is None:
            return self._refusal("supervisor_unavailable")

        prompt = (
            f"Authenticated role: {role}\n"
            f"Permitted document collections: {ROLE_COLLECTIONS[role]}\n"
            f"SQL capability authorized: {role in SQL_RAG_ROLES}\n"
            f"Document capability enabled: {settings.agent_document_enabled}\n"
            f"SQL capability enabled: {settings.agent_sql_enabled}\n"
            f"User question: {question}"
        )
        try:
            response = llm_chat_completion(
                client=self.client,
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": self._SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            decision = RouteDecision.model_validate_json(raw or "")
        except (ValidationError, TypeError, ValueError, KeyError, AttributeError):
            return self._refusal("malformed_supervisor_decision")
        except APIError:
            logger.exception("Supervisor provider request failed")
            return self._refusal("supervisor_error")
        except Exception:
            logger.exception("Unexpected supervisor provider failure")
            return self._refusal("supervisor_error")

        return self._validate_capability(decision, role)

    def _validate_capability(self, decision: RouteDecision, role: str) -> RouteDecision:
        """Apply trusted capability policy after model output validation."""
        if decision.target == RouteTarget.DOCUMENT and not settings.agent_document_enabled:
            return self._refusal("document_capability_disabled")
        if decision.target == RouteTarget.SQL:
            if role not in SQL_RAG_ROLES:
                return self._refusal("sql_role_unauthorized")
            if not settings.agent_sql_enabled:
                return self._refusal("sql_capability_disabled")
        if decision.target in {RouteTarget.DOCUMENT, RouteTarget.SQL}:
            expected = decision.target.value
            if decision.required_capability not in {None, expected}:
                return self._refusal("capability_mismatch")
        return decision

    @staticmethod
    def _refusal(reason: str) -> RouteDecision:
        return RouteDecision(
            target=RouteTarget.REFUSAL,
            rationale=reason,
            confidence=None,
            required_capability=None,
        )
