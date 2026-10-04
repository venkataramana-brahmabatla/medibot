# Document retrieval, reranking, and answer agents

Source: `src/retrieval/router.py`, `hybrid_rag.py`, `reranker.py`,
`src/agents/supervisor.py`, `document.py`, `contracts.py`, and
`src/ingestion/vectorstore.py`.

```mermaid
flowchart TD
    Request[Question and authenticated role] --> Router[QueryRouter.route_and_execute]
    Router --> Supervisor[SupervisorAgent sends constrained routing prompt to Groq]
    Supervisor --> Parse[Validate JSON against RouteDecision contract]
    Parse --> Decision{Route target}
    Decision -- Clarification --> Clarify[Return clarification response]
    Decision -- Refusal or invalid --> Refuse[Return safe supervisor refusal]
    Decision -- SQL --> SQLGate[Check role and SQL capability]
    Decision -- Document --> DocGate[Check document capability]
    DocGate --> Search[HybridRAGPipeline.query]
    Search --> Init[Open local Qdrant and load FastEmbed models]
    Init --> QueryEmb[Embed question as dense and sparse vectors]
    QueryEmb --> Filter[Apply Qdrant access_roles filter for authenticated role]
    Filter --> Candidates[Dense and sparse Prefetch searches]
    Candidates --> RRF[Qdrant reciprocal-rank fusion returns top-k]
    RRF --> HasResults{Any candidates?}
    HasResults -- No --> NoResults[Return role-aware no-results response]
    HasResults -- Yes --> CrossEncoder[SentenceTransformers CrossEncoder scores query/chunks]
    CrossEncoder --> TopN[Keep top-n and remove low relevance scores]
    TopN --> Relevant{Relevant chunks remain?}
    Relevant -- No --> NoResults
    Relevant -- Yes --> Evidence[Build source metadata and evidence context]
    Evidence --> DocAgent[DocumentAnswerAgent asks Groq for typed JSON answer and evidence IDs]
    DocAgent --> Contract[Validate AnswerDraft and evidence IDs]
    Contract --> Valid{Valid grounded answer?}
    Valid -- No or provider unavailable --> Fallback[Extract concise answer from supplied chunks]
    Valid -- Yes --> Sources[Map selected evidence IDs to application-owned citations]
    Fallback --> Result[Return answer, citations and evaluation-only contexts]
    Sources --> Result
    SQLGate -- Unauthorized --> SQLRefuse[Return SQL authorization refusal]
    SQLGate -- Authorized --> SQLPath[Continue in separate SQL RAG flow]
```

The role filter is applied in Qdrant before results are returned to the answer
agent. The document model cannot create citation metadata; valid evidence IDs
are mapped to source records already selected by the application.
