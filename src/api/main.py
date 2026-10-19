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

from collections import defaultdict, deque
import hmac
from threading import Lock
from time import monotonic
from typing import Any, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from rich.console import Console
from langsmith import traceable
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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
    docs_url=None if settings.app_env == "production" else "/docs",
    redoc_url=None if settings.app_env == "production" else "/redoc",
    openapi_url=None if settings.app_env == "production" else "/openapi.json",
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


class _InMemoryRateLimiter:
    """Per-process abuse guard; production deployments should also rate-limit at the proxy."""

    def __init__(self) -> None:
        self._attempts: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._checks = 0

    def allow(self, key: tuple[str, str], maximum: int, window_seconds: int = 60) -> bool:
        now = monotonic()
        cutoff = now - window_seconds
        with self._lock:
            self._checks += 1
            if self._checks % 128 == 0:
                for old_key, old_attempts in list(self._attempts.items()):
                    while old_attempts and old_attempts[0] <= cutoff:
                        old_attempts.popleft()
                    if not old_attempts:
                        self._attempts.pop(old_key, None)
            if key not in self._attempts and len(self._attempts) >= 10_000:
                self._attempts.pop(next(iter(self._attempts)))
            attempts = self._attempts[key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= maximum:
                return False
            attempts.append(now)
            return True


request_limiter = _InMemoryRateLimiter()


class RequestSecurityMiddleware:
    """Enforce bounded request bodies and basic per-process endpoint throttling."""

    _LIMITED_PATHS = {"/login", "/chat"}
    _MAX_BODY_BYTES = 16_384

    def __init__(self, inner_app: ASGIApp):
        self.inner_app = inner_app

    async def _reject(self, scope: Scope, receive: Receive, send: Send, status_code: int, detail: str) -> None:
        response = JSONResponse(status_code=status_code, content={"detail": detail})
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope.get("type") != "http" or path not in self._LIMITED_PATHS:
            await self.inner_app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self._MAX_BODY_BYTES:
                    await self._reject(scope, receive, send, 413, "Request body is too large.")
                    return
            except ValueError:
                await self._reject(scope, receive, send, 400, "Invalid content length.")
                return

        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        maximum = 5 if path == "/login" else 20
        if not request_limiter.allow((client_ip, path), maximum):
            response = JSONResponse(
                status_code=429,
                headers={"Retry-After": "60"},
                content={"detail": "Too many requests. Please retry later."},
            )
            await response(scope, receive, send)
            return

        # Count streamed bodies too, then replay the small bounded body to FastAPI.
        buffered_messages: list[Message] = []
        body_size = 0
        while True:
            message = await receive()
            buffered_messages.append(message)
            if message["type"] != "http.request":
                break
            body_size += len(message.get("body", b""))
            if body_size > self._MAX_BODY_BYTES:
                await self._reject(scope, receive, send, 413, "Request body is too large.")
                return
            if not message.get("more_body", False):
                break

        message_index = 0

        async def replay_body() -> Message:
            nonlocal message_index
            if message_index < len(buffered_messages):
                message = buffered_messages[message_index]
                message_index += 1
                return message
            return await receive()

        await self.inner_app(scope, replay_body, send)


app.add_middleware(RequestSecurityMiddleware)


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
    question: str = Field(
        ..., min_length=1, max_length=4_000, description="User's natural language question"
    )


class SourceCitation(BaseModel):
    source_document: str
    section_title: str
    collection: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceCitation] = Field(default_factory=list)
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
    if not settings.demo_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password login is not configured.",
        )

    user_info = DEMO_USERS.get(request.username.lower())
    password_matches = hmac.compare_digest(request.password, settings.demo_auth_password)
    if not user_info or not password_matches:
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

    console.print(f"🌐 Starting MediBot FastAPI Backend Server on [cyan]{settings.api_host}:{settings.api_port}[/cyan]")
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.app_env == "development",
    )
