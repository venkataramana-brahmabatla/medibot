"""LangSmith tracing helpers shared by the request pipeline."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Iterator

from langsmith import Client, traceable, tracing_context
from langchain_openai import ChatOpenAI
from openai import OpenAI

from src.config import settings

logger = logging.getLogger(__name__)


def create_chat_client(api_key: str | None = None) -> OpenAI | None:
    """Create a sync OpenAI-compatible client for Groq."""
    key = api_key or settings.groq_api_key
    if not key.strip():
        return None
    return OpenAI(
        api_key=key,
        base_url="https://api.groq.com/openai/v1",
        timeout=settings.agent_timeout_seconds,
        max_retries=settings.agent_max_retries,
    )


def create_chat_model(temperature: float = 0) -> ChatOpenAI | None:
    """Create the LangChain wrapper used by OpenEvals and RAGAS."""
    if not settings.groq_api_key.strip():
        return None
    return ChatOpenAI(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        base_url="https://api.groq.com/openai/v1",
        temperature=temperature,
        # Keep RAGAS/OpenEvals completions below Groq's per-minute output cap.
        max_tokens=512,
        timeout=settings.agent_timeout_seconds,
        max_retries=settings.agent_max_retries,
    )


@lru_cache(maxsize=1)
def _langsmith_client() -> Client:
    """Build one client from application settings without logging credentials."""
    return Client(api_key=settings.langsmith_api_key)


@contextmanager
def langsmith_request_context() -> Iterator[None]:
    """Set project/client context for a request, safely disabling tracing if unset."""
    if not settings.langsmith_tracing:
        with tracing_context(enabled=False):
            yield
        return

    if not settings.langsmith_api_key.strip():
        logger.warning("LangSmith tracing is enabled but no API key is configured")
        with tracing_context(enabled=False):
            yield
        return

    try:
        client = _langsmith_client()
    except Exception:
        logger.exception("Could not initialize LangSmith client; tracing disabled for this request")
        with tracing_context(enabled=False):
            yield
        return

    with tracing_context(
        enabled=True,
        client=client,
        project_name=settings.langsmith_project,
        tags=["medibot"],
    ):
        yield


def _trace_inputs_without_client(inputs: dict[str, Any]) -> dict[str, Any]:
    """Keep prompts and model parameters in traces, but never serialize clients."""
    return {key: value for key, value in inputs.items() if key != "client"}


def flush_langsmith_traces() -> None:
    """Flush queued trace writes; primarily useful for short-lived verification jobs."""
    if settings.langsmith_tracing and settings.langsmith_api_key.strip():
        _langsmith_client().flush()


def _chat_completion_outputs(response: Any) -> dict[str, Any]:
    """Capture model text and normalized token usage without serializing SDK internals."""
    choices = getattr(response, "choices", None) or []
    content = None
    if choices:
        content = getattr(getattr(choices[0], "message", None), "content", None)

    outputs: dict[str, Any] = {"content": content}
    usage = getattr(response, "usage", None)
    if usage is not None:
        token_usage = {
            "input_tokens": getattr(usage, "prompt_tokens", None),
            "output_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
        outputs["usage_metadata"] = {
            key: value for key, value in token_usage.items() if value is not None
        }
    return outputs


# Kept for callers/tests written before the provider-neutral trace rename.
_groq_completion_outputs = _chat_completion_outputs


@traceable(
    name="llm_chat_completion",
    run_type="llm",
    process_inputs=_trace_inputs_without_client,
    process_outputs=_chat_completion_outputs,
)
def llm_chat_completion(client: Any, **kwargs: Any) -> Any:
    """Make a provider chat request under an LLM trace with available token usage."""
    return client.chat.completions.create(**kwargs)
