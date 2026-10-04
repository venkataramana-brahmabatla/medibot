from types import SimpleNamespace

from src.observability.tracing import (
    _groq_completion_outputs,
    _trace_inputs_without_client,
)


def test_groq_trace_output_normalizes_usage_metadata():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Synthetic answer"))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=5, total_tokens=17),
    )

    outputs = _groq_completion_outputs(response)

    assert outputs == {
        "content": "Synthetic answer",
        "usage_metadata": {
            "input_tokens": 12,
            "output_tokens": 5,
            "total_tokens": 17,
        },
    }


def test_groq_trace_inputs_never_include_client_credentials():
    fake_client = SimpleNamespace(api_key="must-not-be-recorded")

    inputs = _trace_inputs_without_client(
        {"client": fake_client, "model": "synthetic-model", "messages": []}
    )

    assert inputs == {"model": "synthetic-model", "messages": []}
