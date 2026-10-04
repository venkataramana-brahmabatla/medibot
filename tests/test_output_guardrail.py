from src.guardrails.output import OutputGuardrail, OutputGuardrailVerdict


def successful_hybrid_result(answer="Hand hygiene is required before patient contact."):
    return {
        "answer": answer,
        "sources": [{"collection": "nursing"}],
        "retrieval_type": "hybrid_rag",
        "status": "success",
    }


def test_allows_safe_response_with_permitted_source():
    verdict = OutputGuardrail(evaluator=lambda **_: {"verdict": "allowed", "reason": "test_passed"}).evaluate(
        successful_hybrid_result(),
        "nurse",
    )

    assert verdict.verdict == "allowed"


def test_uses_openevals_verdict_when_configured():
    def evaluator(*, inputs, outputs):
        assert inputs["role"] == "nurse"
        assert outputs["answer"]
        return {"verdict": "blocked", "reason": "unsupported_medical_claim"}

    verdict = OutputGuardrail(evaluator=evaluator).evaluate(successful_hybrid_result(), "nurse")

    assert verdict.verdict == "blocked"
    assert verdict.reason == "unsupported_medical_claim"


def test_openevals_malformed_verdict_fails_closed():
    verdict = OutputGuardrail(evaluator=lambda **_: {"reason": "missing verdict"}).evaluate(
        successful_hybrid_result(),
        "nurse",
    )

    assert verdict.verdict == "blocked"
    assert verdict.reason == "malformed_guardrail_verdict"


def test_blocks_pii_in_response():
    verdict = OutputGuardrail().evaluate(
        successful_hybrid_result("Contact patient PAT-51347 at patient@example.com."),
        "nurse",
    )

    assert verdict.verdict == "blocked"
    assert verdict.reason in {"patient_identifier", "email_address"}


def test_blocks_restricted_source_leak():
    verdict = OutputGuardrail().evaluate(
        {
            **successful_hybrid_result(),
            "sources": [{"collection": "billing"}],
        },
        "nurse",
    )

    assert verdict.verdict == "blocked"
    assert verdict.reason == "restricted_content_leak"


def test_blocks_successful_hybrid_response_without_citations():
    verdict = OutputGuardrail().evaluate(
        {**successful_hybrid_result(), "sources": []},
        "nurse",
    )

    assert verdict.verdict == "blocked"
    assert verdict.reason == "missing_source_citations"


def test_malformed_output_verdict_fails_closed():
    verdict = OutputGuardrail._parse_verdict({"reason": "missing verdict"})

    assert verdict == OutputGuardrailVerdict(
        verdict="blocked",
        reason="malformed_guardrail_verdict",
    )


def test_api_hides_output_guardrail_reason(monkeypatch):
    from src.api import main
    from src.api.auth import UserPayload
    from contextlib import nullcontext

    monkeypatch.setattr(main, "langsmith_request_context", nullcontext)

    class FakeRouter:
        def route_and_execute(self, question, role):
            return {
                **successful_hybrid_result("Patient PAT-12345 email patient@example.com"),
                "role": role,
            }

    monkeypatch.setattr(main, "get_router", lambda: FakeRouter())

    response = main.chat(
        main.ChatRequest(question="What is the nursing protocol?"),
        current_user=UserPayload(username="nurse.priya", role="nurse", full_name="Nurse Priya Sharma"),
    )

    assert response.status == "output_guardrail_blocked"
    assert response.retrieval_type == "output_guardrail"
    assert "patient@example.com" not in response.answer
    assert "email_address" not in response.answer
