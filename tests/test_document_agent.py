from types import SimpleNamespace

from src.agents.document import DocumentAnswerAgent


SOURCES = [
    {
        "source_document": "infection_control.pdf",
        "section_title": "Hand Hygiene",
        "collection": "nursing",
    }
]
CHUNKS = [{"source_document": "infection_control.pdf", "section_title": "Hand Hygiene", "collection": "nursing", "text": "Use hand hygiene before patient contact."}]


class FakeClient:
    def __init__(self, content):
        self.content = content
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


def fallback(question, chunks):
    return "Fallback answer from evidence."


def test_document_agent_returns_typed_answer_draft():
    agent = DocumentAnswerAgent(
        client=FakeClient(
            '{"answer":"Use hand hygiene before patient contact.","evidence_ids":[1]}'
        ),
        model="test-model",
        fallback=fallback,
    )

    draft = agent.answer("What is the protocol?", "nurse", CHUNKS, SOURCES)

    assert draft.answer.startswith("Use hand hygiene")
    assert draft.sources[0].collection == "nursing"


def test_document_agent_falls_back_on_malformed_output():
    agent = DocumentAnswerAgent(
        client=FakeClient('{"answer":""}'),
        model="test-model",
        fallback=fallback,
    )

    draft = agent.answer("What is the protocol?", "nurse", CHUNKS, SOURCES)

    assert draft.answer == "Fallback answer from evidence."
    assert draft.sources[0].source_document == "infection_control.pdf"


def test_document_agent_uses_fallback_without_provider():
    agent = DocumentAnswerAgent(client=None, model="test-model", fallback=fallback)

    draft = agent.answer("What is the protocol?", "nurse", CHUNKS, SOURCES)

    assert draft.answer == "Fallback answer from evidence."
    assert draft.sources[0].source_document == "infection_control.pdf"


def test_document_agent_limits_citations_to_valid_model_selected_evidence():
    chunks = CHUNKS + [
        {
            "source_document": "ppe.pdf",
            "section_title": "Gloves",
            "collection": "nursing",
            "text": "Wear gloves when contact with blood is anticipated.",
        }
    ]
    sources = SOURCES + [
        {
            "source_document": "ppe.pdf",
            "section_title": "Gloves",
            "collection": "nursing",
        }
    ]
    agent = DocumentAnswerAgent(
        client=FakeClient('{"answer":"Use hand hygiene.","evidence_ids":[2,999]}'),
        model="test-model",
        fallback=fallback,
    )

    draft = agent.answer("What is the protocol?", "nurse", chunks, sources)

    assert [source.source_document for source in draft.sources] == ["ppe.pdf"]


def test_document_agent_falls_back_to_supplied_sources_for_empty_citation_selection():
    agent = DocumentAnswerAgent(
        client=FakeClient('{"answer":"Use hand hygiene.","evidence_ids":[]}'),
        model="test-model",
        fallback=fallback,
    )

    draft = agent.answer("What is the protocol?", "nurse", CHUNKS, SOURCES)

    assert draft.answer == "Use hand hygiene."
    assert draft.sources[0].source_document == "infection_control.pdf"


def test_document_agent_contains_provider_and_fallback_errors():
    class RaisingClient:
        chat = SimpleNamespace(completions=None)

        def __init__(self):
            self.chat.completions = self

        def create(self, **kwargs):
            raise RuntimeError("provider failure")

    def raising_fallback(question, chunks):
        raise RuntimeError("fallback failure")

    agent = DocumentAnswerAgent(client=RaisingClient(), model="test-model", fallback=raising_fallback)

    draft = agent.answer("What is the protocol?", "nurse", CHUNKS, SOURCES)

    assert draft.answer == "I couldn't prepare a reliable answer from the retrieved documents."
    assert draft.sources[0].source_document == "infection_control.pdf"
