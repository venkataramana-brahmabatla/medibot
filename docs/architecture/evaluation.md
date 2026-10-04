 # Evaluation pipeline and report generation

Source: `src/evaluation/runner.py`, `dataset.json`, guardrails, router, and
`reports/evaluation_latest.md`.

```mermaid
flowchart TD
    Start([Run python -m src.evaluation.runner]) --> Dataset[Load labeled JSON cases]
    Dataset --> Enabled[Keep cases enabled in dataset]
    Enabled --> Setup[Create router, input/output guardrails and separate Groq judge]
    Setup --> Trace[Open LangSmith evaluation trace context when configured]
    Trace --> Each[Run each case and measure elapsed time]
    Each --> Input[Input guardrail]
    Input --> InputBlock{Blocked?}
    InputBlock -- Yes --> Generic[Use generic refusal; target is not invoked]
    InputBlock -- No --> Target[Run supervisor router and document or SQL RAG]
    Target --> Output[Output guardrail]
    Output --> EndCase[Capture answer, contexts, citations, status, verdicts and latency]
    Generic --> EndCase
    EndCase --> Heuristics[Run 4 deterministic checks]
    Heuristics --> Judge[Separate structured LLM judge scores each case with rubric and justification]
    Judge --> More{More enabled cases?}
    More -- Yes --> Each
    More -- No --> Answerable[Select expected-answer cases for RAGAS]
    Answerable --> RAGAS[Compute faithfulness, answer relevancy, context precision and recall]
    RAGAS --> Metrics[Aggregate metric means and threshold results]
    Metrics --> Report[Write Markdown report with per-case rows, guardrail counts and examples]
    Report --> Verdict{All thresholds and checks pass?}
    Verdict -- Yes --> Exit0[Exit success]
    Verdict -- No --> Exit1[Exit failure; retain report]
```

The report evaluates only enabled cases, while the JSON file may contain more
labeled cases. Refusal cases are judged and checked heuristically; RAGAS is
run on cases whose expected action is `answer`. The judge call is separate
from the chatbot response call, even though both use the configured Groq
model.
