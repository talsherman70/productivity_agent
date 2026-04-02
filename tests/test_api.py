"""
Tests for the API endpoints in app/api/routes.py

We use FastAPI's TestClient which runs requests without a real server.
The orchestrators are mocked so no real API calls to Claude are made.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# ── /health ───────────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_returns_200(self):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_ok_status(self):
        response = client.get("/health")
        assert response.json()["status"] == "ok"

    def test_health_returns_message(self):
        response = client.get("/health")
        assert "message" in response.json()


# ── /chat/new ─────────────────────────────────────────────────────────────────

class TestNewChatEndpoint:
    def test_new_chat_returns_200(self):
        response = client.post("/chat/new")
        assert response.status_code == 200

    def test_new_chat_returns_session_id(self):
        response = client.post("/chat/new")
        data = response.json()
        assert "session_id" in data
        assert len(data["session_id"]) > 0

    def test_new_chat_returns_unique_ids(self):
        id1 = client.post("/chat/new").json()["session_id"]
        id2 = client.post("/chat/new").json()["session_id"]
        assert id1 != id2

    def test_new_chat_returns_message(self):
        response = client.post("/chat/new")
        assert "message" in response.json()


# ── /chat ─────────────────────────────────────────────────────────────────────

MOCK_CHAT_RESPONSE = {
    "session_id": "test-session",
    "assistant_message": "Here's what I came up with:\n\n1. Step one\n2. Step two",
    "structured_data": None,
    "action": "plan_delivered",
}


class TestChatEndpoint:
    def test_chat_with_invalid_session_returns_404(self):
        response = client.post("/chat", json={
            "session_id": "non-existent-session-id",
            "message": "hello"
        })
        assert response.status_code == 404

    def test_chat_with_empty_message_returns_400(self):
        sid = client.post("/chat/new").json()["session_id"]
        response = client.post("/chat", json={"session_id": sid, "message": ""})
        assert response.status_code == 400

    def test_chat_with_whitespace_message_returns_400(self):
        sid = client.post("/chat/new").json()["session_id"]
        response = client.post("/chat", json={"session_id": sid, "message": "   "})
        assert response.status_code == 400

    def test_chat_missing_session_id_returns_422(self):
        response = client.post("/chat", json={"message": "hello"})
        assert response.status_code == 422

    def test_chat_missing_message_returns_422(self):
        sid = client.post("/chat/new").json()["session_id"]
        response = client.post("/chat", json={"session_id": sid})
        assert response.status_code == 422

    def test_chat_valid_request_returns_200(self):
        sid = client.post("/chat/new").json()["session_id"]
        with patch("app.api.routes.ConversationalOrchestrator") as mock_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = {**MOCK_CHAT_RESPONSE, "session_id": sid}
            mock_cls.return_value = mock_orch

            response = client.post("/chat", json={"session_id": sid, "message": "plan my week"})

        assert response.status_code == 200

    def test_chat_response_has_required_fields(self):
        sid = client.post("/chat/new").json()["session_id"]
        with patch("app.api.routes.ConversationalOrchestrator") as mock_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = {**MOCK_CHAT_RESPONSE, "session_id": sid}
            mock_cls.return_value = mock_orch

            response = client.post("/chat", json={"session_id": sid, "message": "hello"})

        data = response.json()
        assert "session_id" in data
        assert "assistant_message" in data
        assert "action" in data

    def test_chat_orchestrator_exception_returns_500(self):
        sid = client.post("/chat/new").json()["session_id"]
        with patch("app.api.routes.ConversationalOrchestrator") as mock_cls:
            mock_orch = MagicMock()
            mock_orch.run.side_effect = Exception("something broke")
            mock_cls.return_value = mock_orch

            response = client.post("/chat", json={"session_id": sid, "message": "hello"})

        assert response.status_code == 500

    def test_chat_missing_api_key_returns_500(self):
        sid = client.post("/chat/new").json()["session_id"]
        with patch("app.api.routes.ConversationalOrchestrator") as mock_cls:
            mock_orch = MagicMock()
            mock_orch.run.side_effect = ValueError("ANTHROPIC_API_KEY not found in .env file")
            mock_cls.return_value = mock_orch

            response = client.post("/chat", json={"session_id": sid, "message": "hello"})

        assert response.status_code == 500
        assert "ANTHROPIC_API_KEY" in response.json()["detail"]


# ── /run ──────────────────────────────────────────────────────────────────────

MOCK_RUN_RESPONSE = {
    "status": "ok",
    "plan": [{"id": 1, "title": "Step one", "estimated_minutes": 30, "priority": "high"}],
    "execution_results": ["Insight one"],
    "critique": "",
    "final_summary": "",
}


class TestRunEndpoint:
    def test_run_with_empty_goal_returns_400(self):
        response = client.post("/run", json={"goal": ""})
        assert response.status_code == 400

    def test_run_with_whitespace_goal_returns_400(self):
        response = client.post("/run", json={"goal": "   "})
        assert response.status_code == 400

    def test_run_missing_goal_returns_422(self):
        response = client.post("/run", json={})
        assert response.status_code == 422

    def test_run_valid_goal_returns_200(self):
        with patch("app.api.routes.Orchestrator") as mock_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = MOCK_RUN_RESPONSE
            mock_cls.return_value = mock_orch

            response = client.post("/run", json={"goal": "Plan my week"})

        assert response.status_code == 200

    def test_run_response_has_required_fields(self):
        with patch("app.api.routes.Orchestrator") as mock_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = MOCK_RUN_RESPONSE
            mock_cls.return_value = mock_orch

            response = client.post("/run", json={"goal": "Plan my week"})

        data = response.json()
        assert "status" in data
        assert "plan" in data
        assert "execution_results" in data

    def test_run_passes_context_to_orchestrator(self):
        with patch("app.api.routes.Orchestrator") as mock_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = MOCK_RUN_RESPONSE
            mock_cls.return_value = mock_orch

            client.post("/run", json={"goal": "Plan my week", "context": "I have 2 hours"})

            mock_orch.run.assert_called_once_with(goal="Plan my week", context="I have 2 hours")

    def test_run_orchestrator_exception_returns_500(self):
        with patch("app.api.routes.Orchestrator") as mock_cls:
            mock_orch = MagicMock()
            mock_orch.run.side_effect = Exception("unexpected failure")
            mock_cls.return_value = mock_orch

            response = client.post("/run", json={"goal": "Plan my week"})

        assert response.status_code == 500


# ── Root UI ───────────────────────────────────────────────────────────────────

class TestRootEndpoint:
    def test_root_returns_200(self):
        response = client.get("/")
        assert response.status_code == 200

    def test_root_returns_html(self):
        response = client.get("/")
        assert "text/html" in response.headers["content-type"]
