# Authorized SQL question path

Source: `src/agents/supervisor.py`, `src/retrieval/router.py`, and
`src/retrieval/sql_rag.py`.

```mermaid
flowchart TD
    Question[Question and authenticated role] --> Supervisor[Groq supervisor chooses SQL route]
    Supervisor --> Contract[Validate structured RouteDecision]
    Contract --> RouterGate{Role authorized and SQL enabled?}
    RouterGate -- No --> RouterRefuse[Safe supervisor refusal]
    RouterGate -- Yes --> SQLRAG[SQLRAG.sql_rag_chain]
    SQLRAG --> RoleGate{Role in billing_executive or admin?}
    RoleGate -- No --> RBAC[Return SQL RBAC refusal; do not query database]
    RoleGate -- Yes --> Generate[Groq generates SQL from schema and question]
    Generate --> Clean[Strip code fences and isolate SQL statement]
    Clean --> ReadOnly{SELECT or WITH passes SQLite authorizer?}
    ReadOnly -- No --> Reject[Reject SQL and return an error response]
    ReadOnly -- Yes --> DB[Execute against local SQLite database]
    DB --> Results[Fetch rows and column names]
    Results --> HasRows{Rows returned?}
    HasRows -- No --> Empty[Return no matching records]
    HasRows -- Yes --> Synthesis[Groq synthesizes a concise answer from query results]
    Synthesis --> Return[Return answer, SQL result context and status]
```

SQLite execution is separate from the LLM: generated queries run on a read-only
connection under an authorizer limited to approved tables, aggregate functions,
and non-identifying columns. Row-level output is rejected. Execution time and
result rows are bounded. Evaluation-only result context is
attached internally and omitted from the public `/chat` response. SQL errors
return generic user-facing messages without query or database details.
