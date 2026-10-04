from types import SimpleNamespace

from src.agents.contracts import RouteDecision, RouteTarget
from src.agents.supervisor import SupervisorAgent
from src.retrieval.router import QueryRouter


def fake_response(payload):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=payload))]
    )


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        return fake_response(self.payload)


def test_supervisor_validates_structured_route():
    supervisor = SupervisorAgent(
        client=FakeClient(
            '{"target":"sql","rationale":"The user requests claim totals.","confidence":0.95,"required_capability":"sql"}'
        )
    )

    decision = supervisor.decide("What is the total claimed amount?", "admin")

    assert decision.target == RouteTarget.SQL
    assert decision.required_capability == "sql"


def test_supervisor_fails_closed_on_malformed_provider_output():
    supervisor = SupervisorAgent(client=FakeClient('{"target":"not-a-route"}'))

    decision = supervisor.decide("What is this?", "nurse")

    assert decision.target == RouteTarget.REFUSAL
    assert decision.rationale == "malformed_supervisor_decision"
    assert decision.confidence is None


def test_supervisor_enforces_sql_role_authorization(monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "agent_sql_enabled", True)
    supervisor = SupervisorAgent(
        client=FakeClient(
            '{"target":"sql","rationale":"The question requests claim totals.","confidence":0.95,"required_capability":"sql"}'
        )
    )

    decision = supervisor.decide("What is the total claimed amount?", "nurse")

    assert decision.target == RouteTarget.REFUSAL
    assert decision.rationale == "sql_role_unauthorized"
    assert decision.confidence is None


def test_supervisor_contains_unexpected_provider_error():
    class RaisingClient:
        chat = SimpleNamespace(completions=None)

        def __init__(self):
            self.chat.completions = self

        def create(self, **kwargs):
            raise RuntimeError("provider failure")

    decision = SupervisorAgent(client=RaisingClient()).decide("Question", "admin")

    assert decision.target == RouteTarget.REFUSAL
    assert decision.rationale == "supervisor_error"
    assert decision.confidence is None


def test_supervisor_fails_closed_when_provider_is_unavailable(monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "")
    supervisor = SupervisorAgent(client=None)

    decision = supervisor.decide("What is this?", "nurse")

    assert decision.target == RouteTarget.REFUSAL
    assert decision.rationale == "supervisor_unavailable"


def test_router_uses_supervisor_instead_of_keywords():
    class FakeSupervisor:
        def decide(self, question, role):
            return RouteDecision(
                target=RouteTarget.CLARIFICATION,
                rationale="Ambiguous request",
                confidence=0.8,
            )

    router = QueryRouter(
        sql_rag=object(),
        hybrid_rag=object(),
        supervisor=FakeSupervisor(),
    )

    result = router.route_and_execute("claims policy in the document", "nurse")

    assert result["status"] == "clarification_required"
