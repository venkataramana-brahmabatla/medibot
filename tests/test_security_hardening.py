import sqlite3
from types import SimpleNamespace

import jwt
import pytest
from fastapi.testclient import TestClient

from src.api import main as api_main
from src.api.auth import DEMO_USERS, create_access_token, verify_token
from src.config import Settings, settings
from src.ingestion.ingest import ProcessedChunk
from src.ingestion.vectorstore import VectorStore
from src.retrieval.sql_rag import SQLRAG
from qdrant_client.models import SparseVector


def test_access_token_requires_expected_issuer_audience_and_role():
    user = DEMO_USERS["admin.sys"]
    token = create_access_token(user)
    assert verify_token(token).role == "admin"

    invalid_role = jwt.encode(
        {
            "sub": "attacker",
            "role": "superuser",
            "full_name": "Attacker",
            "iat": 1,
            "exp": 4_000_000_000,
            "iss": "medibot",
            "aud": "medibot-client",
            "typ": "access",
        },
        settings.jwt_secret_key,
        algorithm="HS256",
    )
    assert verify_token(invalid_role) is None


def test_demo_login_is_disabled_when_demo_mode_is_off(monkeypatch):
    monkeypatch.setattr(api_main.settings, "demo_auth_enabled", False)
    response = TestClient(api_main.app).post(
        "/login", json={"username": "admin.sys", "password": "ignored"}
    )
    assert response.status_code == 503


def test_dev_demo_login_uses_private_shared_password(monkeypatch):
    monkeypatch.setattr(api_main.settings, "demo_auth_enabled", True)
    monkeypatch.setattr(api_main.settings, "demo_auth_password", "private-test-password")
    response = TestClient(api_main.app).post(
        "/login", json={"username": "admin.sys", "password": "private-test-password"}
    )
    assert response.status_code == 200
    assert verify_token(response.json()["access_token"]).role == "admin"


def test_production_settings_reject_demo_authentication():
    with pytest.raises(ValueError, match="DEMO_AUTH_ENABLED"):
        Settings(
            _env_file=None,
            app_env="production",
            debug=False,
            demo_auth_enabled=True,
            demo_auth_password="local-demo-password-is-long",
            jwt_secret_key="s" * 32,
        )


def test_production_settings_require_explicit_external_llm_opt_in():
    with pytest.raises(ValueError, match="ALLOW_EXTERNAL_LLM_DATA"):
        Settings(
            _env_file=None,
            app_env="production",
            debug=False,
            demo_auth_enabled=False,
            jwt_secret_key="s" * 32,
            groq_api_key="provider-key",
            allow_external_llm_data=False,
        )


def test_request_limiter_blocks_after_configured_attempt_count():
    limiter = api_main._InMemoryRateLimiter()
    key = ("127.0.0.1", "/login")
    assert limiter.allow(key, maximum=2)
    assert limiter.allow(key, maximum=2)
    assert not limiter.allow(key, maximum=2)


def test_oversized_login_body_is_rejected_before_authentication():
    response = TestClient(api_main.app).post(
        "/login",
        content=b"x" * 16_385,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413


@pytest.fixture
def analytics_db(tmp_path):
    path = tmp_path / "analytics.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE claims (claim_id TEXT, patient_id TEXT, patient_name TEXT, department TEXT, claimed_amount REAL)"
    )
    connection.execute(
        "INSERT INTO claims VALUES ('C-1', 'P-12345', 'Test Patient', 'cardiology', 50.0)"
    )
    connection.executemany(
        "INSERT INTO claims VALUES (?, ?, ?, ?, ?)",
        [
            ("C-2", "P-23456", "Test Patient 2", "neurology", 25.0),
            ("C-3", "P-34567", "Test Patient 3", "oncology", 75.0),
        ],
    )
    connection.commit()
    connection.close()
    return path


def test_sql_execution_is_read_only_and_hides_patient_fields(analytics_db):
    rag = SQLRAG(db_path=str(analytics_db), api_key="")
    rows, columns = rag.execute_sql("SELECT department, SUM(claimed_amount) FROM claims GROUP BY department")
    assert columns == ["department", "SUM(claimed_amount)"]
    assert rows == [
        ("cardiology", 50.0),
        ("neurology", 25.0),
        ("oncology", 75.0),
    ]

    with pytest.raises(sqlite3.DatabaseError, match="prohibited|not authorized"):
        rag.execute_sql("SELECT patient_name FROM claims")
    with pytest.raises(sqlite3.DatabaseError, match="prohibited|not authorized"):
        rag.execute_sql("DELETE FROM claims")
    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        rag.execute_sql("SELECT randomblob(10000000)")

    connection = sqlite3.connect(analytics_db)
    assert connection.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 3
    connection.close()


def test_sql_execution_enforces_result_row_limit(analytics_db, monkeypatch):
    monkeypatch.setattr(settings, "sql_max_result_rows", 2)
    rag = SQLRAG(db_path=str(analytics_db), api_key="")
    with pytest.raises(ValueError, match="row limit"):
        rag.execute_sql("SELECT department, COUNT(*) FROM claims GROUP BY department")


def test_sql_validation_error_does_not_return_generated_sql(analytics_db, monkeypatch):
    rag = SQLRAG(db_path=str(analytics_db), api_key="")
    monkeypatch.setattr(rag, "generate_sql", lambda _question: "DROP TABLE claims")
    result = rag.sql_rag_chain("summarize claims", "admin")
    assert result["status"] == "error"
    assert "DROP" not in result["answer"]


def test_reingestion_removes_stale_qdrant_points_and_keeps_stable_ids():
    class FakeQdrant:
        def __init__(self):
            self.points = {"obsolete-point": None}

        def upsert(self, collection_name, points):
            for point in points:
                self.points[point.id] = point

        def scroll(self, **_kwargs):
            return ([SimpleNamespace(id=point_id) for point_id in self.points], None)

        def delete(self, collection_name, points_selector):
            for point_id in points_selector.points:
                self.points.pop(point_id, None)

        def get_collection(self, _collection_name):
            return SimpleNamespace(points_count=len(self.points))

    store = VectorStore.__new__(VectorStore)
    store.client = FakeQdrant()
    store._embed_dense = lambda texts: [[0.1, 0.2] for _ in texts]
    store._embed_sparse = lambda texts: [SparseVector(indices=[1], values=[1.0]) for _ in texts]
    chunk = ProcessedChunk(
        text="A current policy chunk with enough content.",
        source_document="policy.md",
        collection="general",
        access_roles=["nurse"],
        section_title="Access",
        chunk_type="text",
    )

    store.store_chunks([chunk])
    assert "obsolete-point" not in store.client.points
    current_ids = set(store.client.points)
    assert len(current_ids) == 1

    store.store_chunks([chunk])
    assert set(store.client.points) == current_ids

    store.store_chunks([])
    assert store.client.points == {}
