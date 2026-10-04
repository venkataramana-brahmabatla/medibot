"""Typed contracts shared by MediBot's agentic runtime.

These models define boundaries between trusted application state, agents, and
deterministic tools. They intentionally contain no provider-specific logic.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    """Base model that rejects undeclared provider output."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RouteTarget(str, Enum):
    """Specialist capability selected by the supervisor."""

    DOCUMENT = "document"
    SQL = "sql"
    CLARIFICATION = "clarification"
    REFUSAL = "refusal"


class ExecutionStatus(str, Enum):
    """Top-level execution state."""

    RECEIVED = "received"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"


class GuardrailResult(ContractModel):
    """Result of an input or output policy gate."""

    name: str = Field(min_length=1)
    verdict: Literal["allowed", "blocked"]
    reason: str = Field(min_length=1)


class RouteDecision(ContractModel):
    """Validated supervisor decision; confidence is an uncalibrated model hint."""

    target: RouteTarget
    rationale: str = Field(min_length=1, max_length=1_000)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    required_capability: Optional[str] = Field(default=None, min_length=1)


class SourceEvidence(ContractModel):
    """A source citation or retrieved evidence item."""

    source_document: str = Field(min_length=1)
    section_title: str = Field(min_length=1)
    collection: str = Field(min_length=1)
    excerpt: Optional[str] = None


class SQLPlan(ContractModel):
    """Agent-proposed SQL plan before deterministic validation."""

    sql: str = Field(min_length=1, max_length=10_000)
    intent: str = Field(min_length=1, max_length=500)
    tables: list[str] = Field(default_factory=list, max_length=10)


class AnswerDraft(ContractModel):
    """Specialist output before the output guardrail runs."""

    answer: str = Field(min_length=1, max_length=20_000)
    sources: list[SourceEvidence] = Field(default_factory=list, max_length=20)


class ToolCallRecord(ContractModel):
    """Safe, auditable record of one deterministic tool invocation."""

    call_id: UUID = Field(default_factory=uuid4)
    tool_name: str = Field(min_length=1)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    success: Optional[bool] = None
    error_code: Optional[str] = None
    input_summary: Optional[str] = Field(default=None, max_length=1_000)
    output_size: Optional[int] = Field(default=None, ge=0)


class AgentError(ContractModel):
    """Structured internal error; API layers decide the user-safe message."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=2_000)
    retryable: bool = False
    step: Optional[str] = Field(default=None, min_length=1)


class AgentState(ContractModel):
    """Complete request-scoped state passed through the agent workflow."""

    request_id: UUID = Field(default_factory=uuid4)
    username: str = Field(min_length=1)
    role: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=10_000)
    allowed_collections: list[str] = Field(default_factory=list)
    sql_allowed: bool = False
    status: ExecutionStatus = ExecutionStatus.RECEIVED
    route: Optional[RouteDecision] = None
    evidence: list[SourceEvidence] = Field(default_factory=list, max_length=50)
    sql_plan: Optional[SQLPlan] = None
    sql_results: Optional[dict[str, Any]] = None
    answer: Optional[AnswerDraft] = None
    guardrails: list[GuardrailResult] = Field(default_factory=list, max_length=20)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list, max_length=100)
    errors: list[AgentError] = Field(default_factory=list, max_length=20)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    steps: int = Field(default=0, ge=0)

    def record_error(self, error: AgentError) -> None:
        """Record a failure and prevent accidental success-shaped state."""
        self.errors.append(error)
        self.status = ExecutionStatus.FAILED

    def complete(self, status: ExecutionStatus) -> None:
        """Close the state with an explicit terminal status."""
        if status not in {
            ExecutionStatus.SUCCEEDED,
            ExecutionStatus.BLOCKED,
            ExecutionStatus.FAILED,
        }:
            raise ValueError("Agent state can only be completed with a terminal status")
        self.status = status
        self.completed_at = datetime.now(timezone.utc)
