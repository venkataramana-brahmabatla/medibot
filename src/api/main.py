"""
src/api/main.py
---------------
Component 5: FastAPI Backend Application for MediBot.

Endpoints:
  - POST /login                : Authenticate demo credentials, return role-tagged JWT token
  - POST /chat                 : Main RAG endpoint (RBAC + Router + Hybrid/SQL RAG)
  - GET  /collections/{role}   : List accessible document collections for role
  - GET  /health               : System health status check
"""

from typing import Any, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from rich.console import Console
from langsmith import traceable

from src.config import settings, ROLE_COLLECTIONS, ALL_ROLES
from src.guardrails.input import InputGuardrail
from src.guardrails.output import OutputGuardrail
from src.api.auth import (
    DEMO_USERS,
    LoginRequest,
    TokenResponse,
    UserPayload,
    create_access_token,
    get_current_user,
)
from src.retrieval.router import QueryRouter
from src.observability.tracing import langsmith_request_context

console = Console()

# Initialize FastAPI App
app = FastAPI(
    title=settings.app_name,
    description="MediBot Advanced RAG & Role-Based Access Control Backend API",
    version="1.0.0",
)

# Enable CORS for Next.js Frontend (runs on localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy singleton router instance
router_instance: Optional[QueryRouter] = None
input_guardrail = InputGuardrail()
output_guardrail = OutputGuardrail()


def get_router() -> QueryRouter:
    """Returns singleton QueryRouter instance."""
    global router_instance
    if router_instance is None:
        console.print("Initializing QueryRouter for FastAPI...")
        router_instance = QueryRouter()
    return router_instance


# -----------------------------------------------------------------------------
# Request & Response Models
# -----------------------------------------------------------------------------
class ChatRequest(BaseModel):
    question: str = Field(..., description="User's natural language question")


class SourceCitation(BaseModel):
    source_document: str
    section_title: str
    collection: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceCitation] = []
    retrieval_type: str
    role: str
    status: str = "success"


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "environment": settings.app_env,
    }


@app.post("/login", response_model=TokenResponse, tags=["Authentication"])
def login(request: LoginRequest) -> TokenResponse:
    """
    Authenticate demo user credentials and return role-tagged JWT access token.
    """
    user_info = DEMO_USERS.get(request.username.lower())
    if not user_info or user_info["password"] != request.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    token = create_access_token(user_info)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        username=user_info["username"],
        role=user_info["role"],
        full_name=user_info["full_name"],
    )


@app.get("/collections/{role}", tags=["RBAC Access Matrix"])
def get_accessible_collections(role: str) -> dict[str, Any]:
    """
    Returns list of document collections accessible to the given role.
    """
    role_clean = role.lower().strip()
    if role_clean not in ALL_ROLES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{role}' not found. Valid roles: {ALL_ROLES}",
        )

    accessible = ROLE_COLLECTIONS.get(role_clean, [])
    return {
        "role": role_clean,
        "accessible_collections": accessible,
    }


@app.post("/chat", response_model=ChatResponse, tags=["RAG Chat Pipeline"])
def chat(
    request: ChatRequest,
    current_user: Optional[UserPayload] = Depends(get_current_user),
) -> ChatResponse:
    with langsmith_request_context():
        return _traced_chat_request(request, current_user)


def _chat_trace_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    request = inputs.get("request")
    user = inputs.get("current_user")
    return {
        "question": getattr(request, "question", None),
        "role": getattr(user, "role", None),
    }


@traceable(
    name="medibot_chat_request",
    run_type="chain",
    process_inputs=_chat_trace_inputs,
)
def _traced_chat_request(
    request: ChatRequest,
    current_user: Optional[UserPayload],
) -> ChatResponse:
    """
    Main RAG endpoint. Accepts question, identifies user role from Bearer token,
    applies RBAC metadata filter, routes to Hybrid RAG or SQL RAG, and returns
    synthesized answer + source citations.
    """
    if not request.question or not request.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question field cannot be empty.",
        )

    # Always use the role carried by the verified JWT; never trust request data.
    active_role = current_user.role

    console.print(f"\n API /chat Request from role: [yellow]{active_role}[/yellow]")

    guardrail_verdict = input_guardrail.evaluate(request.question)
    if guardrail_verdict.verdict != "allowed":
        return ChatResponse(
            answer="I can only help with MediAssist clinical, operational, and authorized analytical questions.",
            sources=[],
            retrieval_type="input_guardrail",
            role=active_role,
            status="input_guardrail_blocked",
        )

    # Instantiate the target pipeline only after the input guardrail allows the request.
    router = get_router()

    # Route and execute query
    result = router.route_and_execute(question=request.question, role=active_role)

    output_verdict = output_guardrail.evaluate(result, active_role)
    if output_verdict.verdict != "allowed":
        return ChatResponse(
            answer="I’m unable to provide that response because it did not pass MediAssist safety checks.",
            sources=[],
            retrieval_type="output_guardrail",
            role=active_role,
            status="output_guardrail_blocked",
        )

    # Format sources into Pydantic models
    formatted_sources = []
    if result.get("sources"):
        for src in result["sources"]:
            formatted_sources.append(
                SourceCitation(
                    source_document=src.get("source_document", "Unknown"),
                    section_title=src.get("section_title", "General"),
                    collection=src.get("collection", "general"),
                )
            )

    return ChatResponse(
        answer=result["answer"],
        sources=formatted_sources,
        retrieval_type=result["retrieval_type"],
        role=active_role,
        status=result.get("status", "success"),
    )


if __name__ == "__main__":
    import uvicorn

    console.print("🌐 Starting MediBot FastAPI Backend Server on [cyan]http://localhost:8000[/cyan]")
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
