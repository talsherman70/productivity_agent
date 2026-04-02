"""
Tests for app/orchestrator/coordinator.py — Orchestrator.

We mock PlannerAgent and ExecutorAgent so no real API calls are made.
We test that the orchestrator chains them correctly and handles failures.
"""
from unittest.mock import MagicMock, patch
from app.orchestrator.coordinator import Orchestrator


MOCK_PLAN = {
    "goal": "Prepare for interview",
    "tasks": [
        {"id": 1, "title": "Review Python", "description": "Study basics", "estimated_minutes": 60, "priority": "high"},
        {"id": 2, "title": "Practice problems", "description": "Solve exercises", "estimated_minutes": 90, "priority": "high"},
    ],
    "total_estimated_minutes": 150,
    "notes": "Focus on fundamentals",
}

MOCK_EXECUTION = {
    "original_plan": MOCK_PLAN,
    "tool_results": {
        "validation": {"valid": True, "issues": []},
        "conflicts": {"over_budget": False, "total_minutes": 150, "available_minutes": 120, "overloaded_tasks": [], "surplus_or_deficit": -30},
        "prioritized_tasks": MOCK_PLAN["tasks"],
        "summary": {"goal": "Prepare for interview", "total_tasks": 2, "total_hours": 2.5, "priority_breakdown": {"high": 2, "medium": 0, "low": 0}, "first_task": "Review Python", "notes": ""},
    },
    "ai_interpretation": {
        "status": "ready",
        "tool_insights": ["Plan covers key topics"],
        "recommended_first_step": "Start with Python review",
        "warnings": [],
        "adjusted_plan_notes": "",
    },
}


def make_orchestrator():
    """Creates an Orchestrator with mocked agents."""
    with patch("app.orchestrator.coordinator.PlannerAgent") as mock_planner_cls, \
         patch("app.orchestrator.coordinator.ExecutorAgent") as mock_executor_cls:

        mock_planner = MagicMock()
        mock_executor = MagicMock()
        mock_planner_cls.return_value = mock_planner
        mock_executor_cls.return_value = mock_executor

        orchestrator = Orchestrator()
        orchestrator.planner = mock_planner
        orchestrator.executor = mock_executor

    return orchestrator, mock_planner, mock_executor


class TestOrchestrator:
    def test_successful_run_returns_ok_status(self):
        orch, planner, executor = make_orchestrator()
        planner.run.return_value = MOCK_PLAN
        executor.run.return_value = MOCK_EXECUTION

        result = orch.run(goal="Prepare for interview")
        assert result["status"] == "ok"

    def test_successful_run_returns_plan_tasks(self):
        orch, planner, executor = make_orchestrator()
        planner.run.return_value = MOCK_PLAN
        executor.run.return_value = MOCK_EXECUTION

        result = orch.run(goal="Prepare for interview")
        assert len(result["plan"]) == 2
        assert result["plan"][0]["title"] == "Review Python"

    def test_planner_called_with_goal_and_context(self):
        orch, planner, executor = make_orchestrator()
        planner.run.return_value = MOCK_PLAN
        executor.run.return_value = MOCK_EXECUTION

        orch.run(goal="My goal", context="some context")
        planner.run.assert_called_once_with(goal="My goal", context="some context")

    def test_executor_called_with_plan(self):
        orch, planner, executor = make_orchestrator()
        planner.run.return_value = MOCK_PLAN
        executor.run.return_value = MOCK_EXECUTION

        orch.run(goal="My goal")
        executor.run.assert_called_once_with(plan=MOCK_PLAN)

    def test_planner_failure_returns_error_status(self):
        orch, planner, executor = make_orchestrator()
        planner.run.return_value = {"error": "Failed to parse JSON", "raw_response": "bad"}

        result = orch.run(goal="My goal")
        assert result["status"] == "error"

    def test_planner_failure_does_not_call_executor(self):
        orch, planner, executor = make_orchestrator()
        planner.run.return_value = {"error": "Failed to parse JSON", "raw_response": "bad"}

        orch.run(goal="My goal")
        executor.run.assert_not_called()

    def test_executor_failure_returns_error_status(self):
        orch, planner, executor = make_orchestrator()
        planner.run.return_value = MOCK_PLAN
        executor.run.return_value = {
            "ai_interpretation": {"error": "parse failed", "raw_response": ""},
            "tool_results": {},
        }

        result = orch.run(goal="My goal")
        assert result["status"] == "error"

    def test_error_response_has_correct_shape(self):
        orch, planner, executor = make_orchestrator()
        planner.run.return_value = {"error": "fail", "raw_response": ""}

        result = orch.run(goal="My goal")
        assert "status" in result
        assert "plan" in result
        assert "execution_results" in result
        assert "critique" in result
        assert "final_summary" in result

    def test_error_response_plan_is_empty_list(self):
        orch, planner, executor = make_orchestrator()
        planner.run.return_value = {"error": "fail", "raw_response": ""}

        result = orch.run(goal="My goal")
        assert result["plan"] == []

    def test_execution_results_include_tool_insights(self):
        orch, planner, executor = make_orchestrator()
        planner.run.return_value = MOCK_PLAN
        executor.run.return_value = MOCK_EXECUTION

        result = orch.run(goal="My goal")
        assert "Plan covers key topics" in result["execution_results"]

    def test_warnings_prefixed_in_execution_results(self):
        orch, planner, executor = make_orchestrator()
        planner.run.return_value = MOCK_PLAN
        execution_with_warning = {
            **MOCK_EXECUTION,
            "ai_interpretation": {
                **MOCK_EXECUTION["ai_interpretation"],
                "warnings": ["Time budget exceeded"],
            },
        }
        executor.run.return_value = execution_with_warning

        result = orch.run(goal="My goal")
        assert any("WARNING:" in r for r in result["execution_results"])
