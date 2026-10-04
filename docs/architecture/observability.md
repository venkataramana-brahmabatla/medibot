# LangSmith tracing and structured logs

Source: `src/observability/tracing.py`, API, agents, retrieval, guardrails,
and evaluation modules.

```mermaid
flowchart TD
    Request[API /chat or evaluation case] --> Context[langsmith_request_context]
    Context --> Enabled{Tracing enabled and LangSmith key configured?}
    Enabled -- No --> Disabled[Disable tracing for this context]
    Enabled -- Yes --> Project[Create cached LangSmith client and set project/tags]
    Project --> Root[Trace root: medibot_chat_request or evaluation_case]
    Root --> InputSpan[input_guardrail span]
    InputSpan --> RouteSpan[query_router and supervisor decision spans]
    RouteSpan --> Branch{Selected capability}
    Branch -- Documents --> Retrieve[qdrant_hybrid_retrieval]
    Retrieve --> Rerank[cross_encoder_reranking]
    Rerank --> Answer[document_answer and llm_chat_completion]
    Branch -- SQL --> SQLGen[sql_generation and llm_chat_completion]
    SQLGen --> SQLExec[sql_execution tool span]
    SQLExec --> SQLAnswer[sql_answer_synthesis and llm_chat_completion]
    Answer --> OutputSpan[output_guardrail span]
    SQLAnswer --> OutputSpan
    InputSpan --> Block[Blocked input ends before router; trace records decision]
    OutputSpan --> Result[Root span returns safe response]
    Model[Groq completion response] --> Usage[Trace output processor captures text and token usage]
    Model -. wrapped call .-> Answer
    Model -. wrapped call .-> SQLGen
    Model -. wrapped call .-> SQLAnswer
    GuardLog[Guardrail verdict] --> JSON[Structured JSON application log: allowed/blocked and internal reason]
    Root --> Duration[LangSmith span durations show request and stage latency]
    Usage --> TraceView[Inspect trace by request in LangSmith project]
    JSON --> TraceView
    Duration --> TraceView
```

When tracing is disabled or the LangSmith API key is absent, the application
continues with tracing disabled. Guardrail decisions are also written as
structured JSON log events. Groq token counts appear when the provider returns
usage data; span durations provide request and stage timing.
