# API, authentication, and request guardrails

Source: `src/api/main.py`, `src/api/auth.py`, `src/guardrails/input.py`, and
`src/guardrails/output.py`.

```mermaid
flowchart TD
    Client[Frontend or API client] --> AuthRoute{Endpoint}
    AuthRoute -- POST /login --> Credentials[Look up demo account]
    Credentials --> DemoMode{Development demo auth enabled?}
    DemoMode -- No --> Disabled[Return 503; production identity provider required]
    DemoMode -- Yes --> Valid{Username and private shared password valid?}
    Valid -- No --> 401[Return 401]
    Valid -- Yes --> JWT[Sign role-bearing JWT with PyJWT]
    JWT --> Token[Return bearer token]
    AuthRoute -- GET /health --> Health[Return service status]
    AuthRoute -- GET /collections/role --> RoleCheck[Validate role and return allowed collections]
    AuthRoute -- POST /chat --> Bearer[Verify bearer JWT]
    Bearer --> User{Authenticated user?}
    User -- No --> Unauthorized[Return 401]
    User -- Yes --> Request[Read question and trusted role from JWT]
    Request --> Empty{Question empty?}
    Empty -- Yes --> BadRequest[Return 400]
    Empty -- No --> Input[InputGuardrail.evaluate]
    Input --> InputRules[Deterministic patterns: injection, RBAC bypass, off-topic, empty input]
    InputRules --> InputVerdict{Structured allowed verdict?}
    InputVerdict -- No or malformed --> InputLog[Log JSON verdict and internal reason]
    InputLog --> GenericInput[Return generic input refusal; do not create router]
    InputVerdict -- Yes --> Route[Initialize router and run target chatbot]
    Route --> Output[OutputGuardrail.evaluate]
    Output --> Deterministic[Check empty answer, PII, restricted citations and missing citations]
    Deterministic --> HardBlock{Deterministic safety issue?}
    HardBlock -- Yes --> OutputLogBlock[Log structured blocked verdict]
    OutputLogBlock --> GenericOutput[Return generic safety refusal]
    HardBlock -- No --> OpenEvals{Groq evaluator configured?}
    OpenEvals -- Yes --> Judge[OpenEvals structured safety judge]
    OpenEvals -- No --> LocalAllow[Allow after deterministic checks]
    Judge --> JudgeValid{Valid allowed verdict?}
    JudgeValid -- No, error, or malformed --> FailClosed[Fail closed and log reason]
    FailClosed --> GenericOutput
    JudgeValid -- Yes --> Final{Verdict}
    Final -- Blocked --> GenericOutput
    Final -- Allowed --> Response[Return answer, citations, route and status]
    LocalAllow --> Response
```

Demo accounts are development-only and require a private password from `.env`.
Login and chat have request size, field length, and per-process rate limits;
production deployments must also configure equivalent limits at the edge.
The input guardrail is deterministic. OpenEvals is used by the output
guardrail when `GROQ_API_KEY` is configured; provider failures and malformed
verdicts block the response. Internal reasons go to application logs, while
the API returns generic safe messages.
