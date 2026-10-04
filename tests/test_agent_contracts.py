import pytest
from pydantic import ValidationError

from src.agents.contracts import (
    AgentError,
    AgentState,
    AnswerDraft,
    ExecutionStatus,
    RouteDecision,
    RouteTarget,
    SourceEvidence,
)


def test_agent_state_carries_trusted_identity_and_route_contract():
    state = AgentState(
        username="nurse.priya",
        role="nurse",
        question="What is the ICU hand hygiene protocol?",
        allowed_collections=["general", "nursing"],
    )
    state.route = RouteDecision(
        target=RouteTarget.DOCUMENT,
        rationale="The question requests document-grounded clinical guidance.",
        confidence=0.98,
        required_capability="document",
    )

    assert state.request_id
    assert state.role == "nurse"
    assert state.route.target == RouteTarget.DOCUMENT


def test_contracts_reject_undeclared_provider_fields():
    with pytest.raises(ValidationError):
        RouteDecision(
            target=RouteTarget.SQL,
            rationale="Analytical question",
            confidence=0.9,
            unexpected_provider_field=True,
        )


def test_answer_contains_only_answer_and_structured_sources():
    answer = AnswerDraft(
        answer="Use hand hygiene before patient contact.",
        sources=[
            SourceEvidence(
                source_document="infection_control.pdf",
                section_title="Hand Hygiene",
                collection="nursing",
            )
        ],
    )

    assert answer.sources[0].collection == "nursing"
    assert not hasattr(answer, "grounded")
    assert not hasattr(answer, "insufficient_evidence")


def test_error_transitions_state_to_failed():
    state = AgentState(
        username="admin.sys",
        role="admin",
        question="How many claims were escalated?",
    )
    state.record_error(AgentError(code="provider_timeout", message="Agent provider timed out"))

    assert state.status == ExecutionStatus.FAILED
    assert state.errors[0].retryable is False


def test_state_completion_requires_terminal_status():
    state = AgentState(
        username="admin.sys",
        role="admin",
        question="How many claims were escalated?",
    )

    with pytest.raises(ValueError):
        state.complete(ExecutionStatus.RUNNING)
