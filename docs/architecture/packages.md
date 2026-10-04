# Package inventory

This inventory covers the direct dependencies declared in `requirements.txt`
and `frontend/package.json`. Transitive dependencies installed by those
packages are not listed individually.

## Python runtime and application packages

| Package | Where it is used | Purpose |
|---|---|---|
| `pydantic` | Config, agent contracts, guardrail verdicts, API and evaluation schemas | Validate settings and structured inputs/outputs. |
| `pydantic-settings` | `src/config.py` | Load typed application settings from `.env` and environment variables. |
| `python-dotenv` | Settings environment-file support | Provides dotenv parsing support used by settings configuration. |
| `rich` | API, ingestion, retrieval and SQL modules | Render progress, summaries, warnings and terminal output. |
| `fastapi` | `src/api/main.py`, `auth.py` | Define HTTP endpoints, dependencies, request validation and CORS middleware. |
| `uvicorn[standard]` | `src/api/main.py` entry point | Run the FastAPI ASGI application. |
| `PyJWT` | `src/api/auth.py` as `jwt` | Sign and verify role-bearing bearer tokens. |
| `python-multipart` | Not imported by current API code | FastAPI form-upload support; current login accepts JSON, so this looks unused. |
| `openai` | `src/observability/tracing.py`, agents and Groq calls | OpenAI-compatible Python client pointed at Groq's API endpoint. No OpenAI-hosted model is selected by this code. |
| `langchain-openai` | `src/observability/tracing.py` | Supplies `ChatOpenAI` wrappers used by OpenEvals and RAGAS, configured to call Groq. |
| `langchain-community` | `src/evaluation/runner.py` | Supplies local Hugging Face sentence-transformer embeddings to RAGAS. |
| `langsmith` | API, agents, retrieval, guardrails, evaluation, vector search | Add hierarchical traces/spans and LangSmith client/context handling. |
| `openevals` | `src/guardrails/output.py` | Run the structured semantic safety judge for output guardrail decisions. |
| `ragas` | `src/evaluation/runner.py` | Compute faithfulness, answer relevancy, context precision and context recall. |

## Ingestion, retrieval and model packages

| Package | Where it is used | Purpose |
|---|---|---|
| `docling` | `src/ingestion/ingest.py` | Parse source PDFs into structured Docling documents. |
| `docling-core` | `src/ingestion/ingest.py` | Provide `DoclingDocument` types and the structure-aware `HybridChunker`. |
| `qdrant-client` | `src/ingestion/vectorstore.py` | Create and query the local persistent vector collection, payload filters, vector prefetch and RRF fusion. |
| `fastembed` | `src/ingestion/vectorstore.py` | Create local dense vectors and sparse BM25 vectors for indexing and query. |
| `sentence-transformers` | `src/retrieval/reranker.py`; also used by local RAGAS embeddings | Load the cross-encoder reranker and embedding models. |
| `torch` | Used underneath Sentence Transformers | Neural model runtime for cross-encoder scoring and local embedding work. |

## SQL, testing and utility packages

| Package | Where it is used | Purpose / current status |
|---|---|---|
| `sqlparse` | Not imported by current source | Declared for SQL parsing, but `SQLRAG.clean_sql` currently uses regular expressions and SQLite execution instead. |
| `tabulate` | Not imported by current source | Declared for tabular formatting; current console tables use Rich. |
| `passlib[bcrypt]` | Not imported by current source | Password hashing support; current demo account passwords are compared directly in `src/api/auth.py`. |
| `bcrypt` | Not imported directly by current source | Backend for Passlib hashing; currently appears unused together with Passlib. |
| `pytest` | `tests/` | Run the automated Python tests. |
| `requests` | Not imported by current source | General-purpose HTTP client; not currently used by application or tests. |

The unused-package notes are based on imports and code paths in this checkout;
remove a requirement only after confirming no external deployment script relies
on it.

## Frontend packages

| Package | Declared as | Purpose |
|---|---|---|
| `next` | Runtime dependency | Next.js app framework, routes, development server and production build. |
| `react`, `react-dom` | Runtime dependencies | Component model and browser DOM rendering. |
| `lucide-react` | Runtime dependency | Icons used by the interface. |
| `tailwindcss`, `@tailwindcss/postcss` | Development dependencies | Utility CSS and its PostCSS integration. |
| `eslint`, `eslint-config-next` | Development dependencies | Lint rules and Next.js-specific checks. |
| `typescript`, `@types/node`, `@types/react`, `@types/react-dom` | Development dependencies | TypeScript compiler and type declarations. |

## Configuration and model notes

- `GROQ_API_KEY` and `GROQ_MODEL` configure all hosted LLM calls. The OpenAI
  SDK packages here provide a compatible client interface; they do not mean
  requests go to OpenAI.
- Dense and sparse embedding models and the reranker are configured in
  `src/config.py`; FastEmbed and Sentence Transformers run those models locally
  after their model files are available.
- LangSmith, OpenEvals and RAGAS are distinct: LangSmith records traces,
  OpenEvals makes an output-safety decision, and RAGAS computes evaluation
  metrics.
