"""
src/config.py
-------------
Central configuration for MediBot.

All settings are read from the .env file using pydantic-settings.
Import this module wherever you need a setting — do NOT read os.environ directly.

Usage:
    from src.config import settings
    print(settings.groq_model)
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """
    MediBot application settings.
    Values are loaded from the .env file automatically.
    """

    # -------------------------------------------------------------------------
    # App
    # -------------------------------------------------------------------------
    app_name: str = Field(default="MediBot", description="Application name")
    app_env: str = Field(default="development", description="Environment (development / production)")
    debug: bool = Field(default=True, description="Enable debug mode")

    # -------------------------------------------------------------------------
    # LLM (Groq API)
    # -------------------------------------------------------------------------
    groq_api_key: str = Field(default="", description="Your Groq API key from console.groq.com")
    groq_model: str = Field(default="qwen/qwen3.8-27b", description="Groq model name to use for all LLM calls")

    # -------------------------------------------------------------------------
    # LangSmith tracing
    # -------------------------------------------------------------------------
    langsmith_tracing: bool = Field(default=False, description="Enable LangSmith request tracing")
    langsmith_api_key: str = Field(default="", description="LangSmith API key")
    langsmith_project: str = Field(default="medibot", description="LangSmith tracing project")

    # -------------------------------------------------------------------------
    # Evaluation pipeline
    # -------------------------------------------------------------------------
    evaluation_latency_limit_seconds: float = Field(
        default=30.0, gt=0, le=600, description="Maximum response latency for evaluation checks"
    )
    evaluation_ragas_threshold: float = Field(
        default=0.70, ge=0, le=1, description="Minimum aggregate score for each RAGAS metric"
    )
    evaluation_judge_threshold: float = Field(
        default=4.0, ge=1, le=5, description="Minimum mean structured judge score (1-5)"
    )

    # -------------------------------------------------------------------------
    # Storage & Paths
    # -------------------------------------------------------------------------
    data_dir: str = Field(default="./data", description="Root directory for all data files")
    docs_dir: str = Field(default="./data/documents", description="Directory where source PDFs are stored")
    db_path: str = Field(default="./data/documents/db/mediassist.db", description="Path to the SQLite database (SQL RAG)")

    # -------------------------------------------------------------------------
    # Embedding Models (downloaded by fastembed on first run, then cached)
    # -------------------------------------------------------------------------
    dense_embedding_model: str = Field(default="BAAI/bge-small-en-v1.5", description="Dense (semantic) embedding model")
    reranker_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        description="Cross-encoder model used to rerank retrieved chunks",
    )
    sparse_embedding_model: str = Field(default="Qdrant/bm25", description="Sparse (BM25 keyword) embedding model")

    # -------------------------------------------------------------------------
    # Qdrant Vector Database (persistent local storage)
    # -------------------------------------------------------------------------
    qdrant_path: str = Field(default="./data/qdrant_db", description="Local folder where Qdrant stores its data")

    # -------------------------------------------------------------------------
    # JWT / Authentication
    # -------------------------------------------------------------------------
    jwt_secret_key: str = Field(default="medibot-dev-secret-change-in-prod", description="Secret key for signing JWT tokens")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_expiry_hours: int = Field(default=8, description="JWT token expiry in hours")

    # -------------------------------------------------------------------------
    # RAG Pipeline Settings
    # -------------------------------------------------------------------------
    retrieval_top_k: int = Field(default=10, description="How many chunks to fetch from Qdrant (broad set)")
    rerank_top_n: int = Field(default=3, description="How many chunks to keep after reranking (sent to LLM)")

    # -------------------------------------------------------------------------
    # Agent Runtime
    # -------------------------------------------------------------------------
    agent_timeout_seconds: float = Field(default=30.0, gt=0, le=300, description="Timeout for each agent provider request")
    agent_max_retries: int = Field(default=2, ge=0, le=5, description="Maximum retries for agent provider requests")
    agent_document_enabled: bool = Field(default=True, description="Enable the document specialist capability")
    agent_sql_enabled: bool = Field(default=True, description="Enable the SQL specialist capability")

    # -------------------------------------------------------------------------
    # Pydantic config: read from .env file
    # -------------------------------------------------------------------------
    model_config = SettingsConfigDict(
        # Resolve from the repository, not the process working directory. This
        # keeps IDE run configurations and absolute script invocations working.
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore unknown keys in .env
    )


# Create a single global instance — import this everywhere
settings = Settings()


# -------------------------------------------------------------------------
# RBAC: Role → allowed document collections
# This is the source of truth for access control.
# -------------------------------------------------------------------------
ROLE_COLLECTIONS: dict[str, list[str]] = {
    "doctor":            ["general", "clinical", "nursing"],
    "nurse":             ["general", "nursing"],
    "billing_executive": ["general", "billing"],
    "technician":        ["general", "equipment"],
    "admin":             ["general", "clinical", "nursing", "billing", "equipment"],
}

# All valid roles
ALL_ROLES = list(ROLE_COLLECTIONS.keys())

# Roles that are allowed to use SQL RAG (analytical questions)
SQL_RAG_ROLES = ["billing_executive", "admin"]

# All document collection names
ALL_COLLECTIONS = ["general", "clinical", "nursing", "billing", "equipment"]
