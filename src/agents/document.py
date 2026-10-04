"""Evidence-grounded document answer specialist."""

import logging
from typing import Any, Callable, Optional

from openai import APIError
from langsmith import traceable
from pydantic import Field, StrictInt, ValidationError

from src.agents.contracts import AnswerDraft, ContractModel, SourceEvidence
from src.observability.tracing import llm_chat_completion

logger = logging.getLogger(__name__)


class _DocumentAnswerResponse(ContractModel):
    """Provider response; evidence IDs are checked against supplied chunks."""

    answer: str = Field(min_length=1, max_length=20_000)
    evidence_ids: list[StrictInt] = Field(default_factory=list, max_length=50)


class DocumentAnswerAgent:
    """Synthesizes answers from supplied evidence only."""

    _SYSTEM_PROMPT = (
        "You are MediBot's document-answer specialist. "
        "Answer only from the supplied evidence. Be concise and answer the exact "
        "question. Do not disclose information outside the evidence or infer "
        "patient identifiers. Return only JSON with answer and evidence_ids. "
        "evidence_ids must contain only the integer IDs of evidence items that "
        "support the answer. Do not create citations or source metadata."
    )

    def __init__(
        self,
        client: Optional[Any],
        model: str,
        fallback: Callable[[str, list[dict[str, Any]]], str],
    ):
        self.client = client
        self.model = model
        self.fallback = fallback

    @traceable(name="document_answer", run_type="chain")
    def answer(
        self,
        question: str,
        role: str,
        chunks: list[dict[str, Any]],
        sources: list[dict[str, str]],
    ) -> AnswerDraft:
        """Return a typed answer draft, using deterministic extraction offline."""
        evidence = [
            (
                f"[Evidence {index}: {chunk.get('source_document', 'Unknown')} | "
                f"Section: {chunk.get('section_title', 'General')}]\n"
                f"{chunk.get('text', '')}"
            )
            for index, chunk in enumerate(chunks, 1)
        ]
        try:
            source_models = [SourceEvidence.model_validate(source) for source in sources]
        except (ValidationError, TypeError, ValueError):
            logger.exception("Invalid source metadata passed to document answer specialist")
            source_models = []

        if self.client is None:
            return self._fallback_draft(question, chunks, source_models)

        evidence_text = "\n\n".join(evidence)
        prompt = (
            f"Authenticated role: {role}\n"
            f"User question: {question}\n\n"
            f"Evidence:\n{evidence_text}"
        )
        try:
            response = llm_chat_completion(
                client=self.client,
                model=self.model,
                messages=[
                    {"role": "system", "content": self._SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=512,
                response_format={"type": "json_object"},
            )
            response_draft = _DocumentAnswerResponse.model_validate_json(
                response.choices[0].message.content or ""
            )
            selected_sources = self._select_sources(
                response_draft.evidence_ids, chunks, source_models
            )
            return AnswerDraft(answer=response_draft.answer, sources=selected_sources)
        except (ValidationError, TypeError, ValueError, KeyError, AttributeError, APIError):
            logger.exception("Document answer provider returned an unusable response")
            return self._fallback_draft(question, chunks, source_models)
        except Exception:
            logger.exception("Unexpected document answer provider failure")
            return self._fallback_draft(question, chunks, source_models)

    @staticmethod
    def _select_sources(
        evidence_ids: list[int],
        chunks: list[dict[str, Any]],
        sources: list[SourceEvidence],
    ) -> list[SourceEvidence]:
        """Map model-selected evidence IDs to supplied, application-owned sources."""
        valid_ids = {evidence_id for evidence_id in evidence_ids if 1 <= evidence_id <= len(chunks)}
        if not valid_ids:
            return sources

        source_by_key = {
            (source.source_document, source.section_title, source.collection): source
            for source in sources
        }
        selected: list[SourceEvidence] = []
        seen: set[tuple[str, str, str]] = set()
        for index, chunk in enumerate(chunks, 1):
            if index not in valid_ids:
                continue
            key = (
                str(chunk.get("source_document", "Unknown")),
                str(chunk.get("section_title", "General")),
                str(chunk.get("collection", "general")),
            )
            source = source_by_key.get(key)
            if source is not None and key not in seen:
                selected.append(source)
                seen.add(key)
        return selected or sources

    def _fallback_draft(
        self,
        question: str,
        chunks: list[dict[str, Any]],
        sources: list[SourceEvidence],
    ) -> AnswerDraft:
        try:
            answer = self.fallback(question, chunks)
            return AnswerDraft(answer=answer, sources=sources)
        except Exception:
            logger.exception("Document answer fallback failed")
            return AnswerDraft(
                answer="I couldn't prepare a reliable answer from the retrieved documents.",
                sources=sources,
            )
