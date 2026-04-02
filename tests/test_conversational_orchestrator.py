"""
Tests for app/orchestrator/conversational_orchestrator.py

We mock all external calls (LLMClient, Orchestrator pipeline) so no
real API calls are made. We test every intent route and edge case.
"""
import json
from unittest.mock import MagicMock, patch
from app.core.session_store import InMemorySessionStore
from app.orchestrator.conversational_orchestrator import ConversationalOrchestrator


MOCK_PLAN_RESULT = {
    "status": "ok",
    "plan": [
        {"id": 1, "title": "Step one", "estimated_minutes": 30, "priority": "high"},
        {"id": 2, "title": "Step two", "estimated_minutes": 45, "priority": "medium"},
    ],
    "execution_results": ["Insight one"],
    "critique": "",
    "final_summary": "",
}


def intent_response(intent, goal="test goal", context=""):
    return json.dumps({"intent": intent, "goal": goal, "context": context})


def make_orchestrator():
    """
    Creates a ConversationalOrchestrator with:
    - A fresh in-memory store
    - Mocked LLMClient (both self.llm and self.fast_llm)
    - Mocked pipeline
    """
    store = InMemorySessionStore()

    with patch("app.orchestrator.conversational_orchestrator.LLMClient"), \
         patch("app.orchestrator.conversational_orchestrator.Orchestrator"):

        orch = ConversationalOrchestrator(store=store)

    # Replace with clean mocks
    orch.llm = MagicMock()
    orch.fast_llm = MagicMock()
    orch.pipeline = MagicMock()
    orch.pipeline.run.return_value = MOCK_PLAN_RESULT

    return orch, store


class TestConversationalOrchestratorRouting:
    def test_new_goal_runs_pipeline(self):
        orch, store = make_orchestrator()
        sid = store.create_session()
        orch.fast_llm.chat_with_history.return_value = intent_response("new_goal")

        orch.run(session_id=sid, user_message="I want to study Python")

        orch.pipeline.run.assert_called_once()

    def test_confirmation_runs_pipeline(self):
        orch, store = make_orchestrator()
        sid = store.create_session()
        orch.fast_llm.chat_with_history.return_value = intent_response("confirmation", goal="study Python")

        orch.run(session_id=sid, user_message="yes go ahead")

        orch.pipeline.run.assert_called_once()

    def test_needs_context_does_not_run_pipeline(self):
        orch, store = make_orchestrator()
        sid = store.create_session()
        orch.fast_llm.chat_with_history.return_value = intent_response("needs_context", goal="book restaurant")
        orch.llm.chat_with_history.return_value = "What type of cuisine are you in the mood for?"

        orch.run(session_id=sid, user_message="book me a restaurant")

        orch.pipeline.run.assert_not_called()

    def test_needs_context_returns_question(self):
        orch, store = make_orchestrator()
        sid = store.create_session()
        orch.fast_llm.chat_with_history.return_value = intent_response("needs_context")
        orch.llm.chat_with_history.return_value = "What type of cuisine?"

        result = orch.run(session_id=sid, user_message="book me a restaurant")

        assert result["assistant_message"] == "What type of cuisine?"

    def test_rejection_does_not_run_pipeline(self):
        orch, store = make_orchestrator()
        sid = store.create_session()
        orch.fast_llm.chat_with_history.return_value = intent_response("rejection")
        orch.llm.chat_with_history.return_value = "No problem, what would you like instead?"

        orch.run(session_id=sid, user_message="no thanks")

        orch.pipeline.run.assert_not_called()

    def test_refinement_runs_pipeline(self):
        orch, store = make_orchestrator()
        sid = store.create_session()
        orch.fast_llm.chat_with_history.return_value = intent_response("refinement", goal="updated goal")

        orch.run(session_id=sid, user_message="actually make it shorter")

        orch.pipeline.run.assert_called_once()

    def test_other_intent_does_not_run_pipeline(self):
        orch, store = make_orchestrator()
        sid = store.create_session()
        orch.fast_llm.chat_with_history.return_value = intent_response("other")
        orch.llm.chat_with_history.return_value = "Hello! How can I help you?"

        orch.run(session_id=sid, user_message="hello")

        orch.pipeline.run.assert_not_called()

    def test_question_intent_does_not_run_pipeline(self):
        orch, store = make_orchestrator()
        sid = store.create_session()
        orch.fast_llm.chat_with_history.return_value = intent_response("question")
        orch.llm.chat_with_history.return_value = "I can help you plan and organise tasks."

        orch.run(session_id=sid, user_message="what can you do?")

        orch.pipeline.run.assert_not_called()


class TestConversationalOrchestratorHistory:
    def test_user_message_saved_to_history(self):
        orch, store = make_orchestrator()
        sid = store.create_session()
        orch.fast_llm.chat_with_history.return_value = intent_response("other")
        orch.llm.chat_with_history.return_value = "Hi!"

        orch.run(session_id=sid, user_message="hello there")

        history = store.get_history(sid)
        user_msgs = [m for m in history.get_messages() if m["role"] == "user"]
        assert user_msgs[-1]["content"] == "hello there"

    def test_assistant_reply_saved_to_history(self):
        orch, store = make_orchestrator()
        sid = store.create_session()
        orch.fast_llm.chat_with_history.return_value = intent_response("other")
        orch.llm.chat_with_history.return_value = "Here to help!"

        orch.run(session_id=sid, user_message="hello")

        history = store.get_history(sid)
        assistant_msgs = [m for m in history.get_messages() if m["role"] == "assistant"]
        assert assistant_msgs[-1]["content"] == "Here to help!"

    def test_history_grows_with_each_turn(self):
        orch, store = make_orchestrator()
        sid = store.create_session()
        orch.fast_llm.chat_with_history.return_value = intent_response("other")
        orch.llm.chat_with_history.return_value = "response"

        orch.run(session_id=sid, user_message="message 1")
        orch.run(session_id=sid, user_message="message 2")

        history = store.get_history(sid)
        assert len(history.get_messages()) == 4  # 2 user + 2 assistant

    def test_session_id_in_response(self):
        orch, store = make_orchestrator()
        sid = store.create_session()
        orch.fast_llm.chat_with_history.return_value = intent_response("other")
        orch.llm.chat_with_history.return_value = "hi"

        result = orch.run(session_id=sid, user_message="hello")

        assert result["session_id"] == sid


class TestConversationalOrchestratorEdgeCases:
    def test_unknown_session_returns_error(self):
        orch, store = make_orchestrator()

        result = orch.run(session_id="bad-id", user_message="hello")

        assert result["action"] == "error"
        assert "not found" in result["assistant_message"].lower()

    def test_pipeline_error_returns_error_action(self):
        orch, store = make_orchestrator()
        sid = store.create_session()
        orch.fast_llm.chat_with_history.return_value = intent_response("new_goal")
        orch.pipeline.run.return_value = {"status": "error", "final_summary": "Planner failed"}

        result = orch.run(session_id=sid, user_message="plan something")

        assert result["action"] == "error"

    def test_intent_parse_failure_falls_back_to_other(self):
        orch, store = make_orchestrator()
        sid = store.create_session()
        # Return invalid JSON from intent detector
        orch.fast_llm.chat_with_history.return_value = "this is not json"
        orch.llm.chat_with_history.return_value = "fallback response"

        result = orch.run(session_id=sid, user_message="hello")

        # Should not crash — falls back to conversational response
        assert "assistant_message" in result
        orch.pipeline.run.assert_not_called()

    def test_new_goal_with_no_goal_string_falls_back(self):
        orch, store = make_orchestrator()
        sid = store.create_session()
        # Intent is new_goal but goal field is empty
        orch.fast_llm.chat_with_history.return_value = intent_response("new_goal", goal="")
        orch.llm.chat_with_history.return_value = "fallback response"

        result = orch.run(session_id=sid, user_message="do something")

        # No goal → pipeline should NOT run
        orch.pipeline.run.assert_not_called()

    def test_plan_delivered_action_on_success(self):
        orch, store = make_orchestrator()
        sid = store.create_session()
        orch.fast_llm.chat_with_history.return_value = intent_response("new_goal")

        result = orch.run(session_id=sid, user_message="plan my week")

        assert result["action"] == "plan_delivered"

    def test_response_contains_numbered_list(self):
        orch, store = make_orchestrator()
        sid = store.create_session()
        orch.fast_llm.chat_with_history.return_value = intent_response("new_goal")

        result = orch.run(session_id=sid, user_message="plan my week")

        assert "1." in result["assistant_message"]
        assert "2." in result["assistant_message"]
