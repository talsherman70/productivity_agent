"""
Tests for app/tools/productivity.py

These are pure functions — no API calls, no mocking needed.
We test every normal case and every edge case.
"""
import pytest
from app.tools.productivity import (
    validate_plan,
    detect_schedule_conflicts,
    prioritize_tasks,
    summarize_plan,
)

# ── Shared test data ──────────────────────────────────────────────────────────

VALID_TASK = {
    "id": 1,
    "title": "Study Python basics",
    "description": "Review data types and functions",
    "estimated_minutes": 60,
    "priority": "high",
}


def make_tasks(*overrides):
    """Helper: create a list of valid tasks with optional field overrides."""
    tasks = []
    for i, override in enumerate(overrides):
        t = {**VALID_TASK, "id": i + 1}
        t.update(override)
        tasks.append(t)
    return tasks


# ── validate_plan ─────────────────────────────────────────────────────────────

class TestValidatePlan:
    def test_valid_tasks_returns_valid_true(self):
        result = validate_plan(make_tasks({}, {}))
        assert result["valid"] is True
        assert result["issues"] == []

    def test_empty_list_returns_invalid(self):
        result = validate_plan([])
        assert result["valid"] is False
        assert len(result["issues"]) > 0

    def test_missing_title_is_flagged(self):
        result = validate_plan(make_tasks({"title": ""}))
        assert result["valid"] is False
        assert any("title" in issue for issue in result["issues"])

    def test_missing_description_is_flagged(self):
        result = validate_plan(make_tasks({"description": ""}))
        assert result["valid"] is False
        assert any("description" in issue for issue in result["issues"])

    def test_invalid_priority_is_flagged(self):
        result = validate_plan(make_tasks({"priority": "urgent"}))
        assert result["valid"] is False
        assert any("priority" in issue for issue in result["issues"])

    def test_all_valid_priorities_accepted(self):
        for priority in ("high", "medium", "low"):
            result = validate_plan(make_tasks({"priority": priority}))
            assert result["valid"] is True, f"Priority '{priority}' should be valid"

    def test_missing_estimated_minutes_is_flagged(self):
        result = validate_plan(make_tasks({"estimated_minutes": None}))
        assert result["valid"] is False
        assert any("time estimate" in issue for issue in result["issues"])

    def test_estimated_minutes_as_float_is_valid(self):
        result = validate_plan(make_tasks({"estimated_minutes": 45.5}))
        assert result["valid"] is True

    def test_multiple_issues_all_reported(self):
        result = validate_plan(make_tasks({"title": "", "description": "", "priority": "bad"}))
        assert len(result["issues"]) >= 3

    def test_single_valid_task(self):
        result = validate_plan([VALID_TASK])
        assert result["valid"] is True


# ── detect_schedule_conflicts ─────────────────────────────────────────────────

class TestDetectScheduleConflicts:
    def test_under_budget_no_conflict(self):
        tasks = make_tasks({"estimated_minutes": 30}, {"estimated_minutes": 30})
        result = detect_schedule_conflicts(tasks, available_minutes_per_day=120)
        assert result["over_budget"] is False
        assert result["overloaded_tasks"] == []

    def test_over_budget_flagged(self):
        tasks = make_tasks({"estimated_minutes": 90}, {"estimated_minutes": 90})
        result = detect_schedule_conflicts(tasks, available_minutes_per_day=120)
        assert result["over_budget"] is True

    def test_exactly_at_budget_not_over(self):
        tasks = make_tasks({"estimated_minutes": 60}, {"estimated_minutes": 60})
        result = detect_schedule_conflicts(tasks, available_minutes_per_day=120)
        assert result["over_budget"] is False

    def test_total_minutes_calculated_correctly(self):
        tasks = make_tasks({"estimated_minutes": 45}, {"estimated_minutes": 55})
        result = detect_schedule_conflicts(tasks, available_minutes_per_day=200)
        assert result["total_minutes"] == 100

    def test_surplus_calculated_correctly(self):
        tasks = make_tasks({"estimated_minutes": 30})
        result = detect_schedule_conflicts(tasks, available_minutes_per_day=120)
        assert result["surplus_or_deficit"] == 90

    def test_deficit_is_negative(self):
        tasks = make_tasks({"estimated_minutes": 180})
        result = detect_schedule_conflicts(tasks, available_minutes_per_day=120)
        assert result["surplus_or_deficit"] == -60

    def test_overloaded_tasks_named_correctly(self):
        tasks = make_tasks(
            {"estimated_minutes": 100, "title": "Task A"},
            {"estimated_minutes": 100, "title": "Task B"},
        )
        result = detect_schedule_conflicts(tasks, available_minutes_per_day=120)
        assert "Task B" in result["overloaded_tasks"]

    def test_empty_tasks_no_conflict(self):
        result = detect_schedule_conflicts([], available_minutes_per_day=120)
        assert result["over_budget"] is False
        assert result["total_minutes"] == 0

    def test_default_budget_is_120(self):
        tasks = make_tasks({"estimated_minutes": 121})
        result = detect_schedule_conflicts(tasks)
        assert result["over_budget"] is True


# ── prioritize_tasks ──────────────────────────────────────────────────────────

class TestPrioritizeTasks:
    def test_high_comes_before_medium_and_low(self):
        tasks = make_tasks(
            {"priority": "low"},
            {"priority": "high"},
            {"priority": "medium"},
        )
        result = prioritize_tasks(tasks)
        priorities = [t["priority"] for t in result]
        assert priorities.index("high") < priorities.index("medium")
        assert priorities.index("medium") < priorities.index("low")

    def test_same_priority_shorter_task_first(self):
        tasks = make_tasks(
            {"priority": "high", "estimated_minutes": 90},
            {"priority": "high", "estimated_minutes": 30},
        )
        result = prioritize_tasks(tasks)
        assert result[0]["estimated_minutes"] == 30

    def test_recommended_order_added(self):
        tasks = make_tasks({}, {}, {})
        result = prioritize_tasks(tasks)
        orders = [t["recommended_order"] for t in result]
        assert orders == [1, 2, 3]

    def test_original_list_not_mutated(self):
        tasks = make_tasks({"priority": "low"}, {"priority": "high"})
        original_first_priority = tasks[0]["priority"]
        prioritize_tasks(tasks)
        assert tasks[0]["priority"] == original_first_priority

    def test_empty_list_returns_empty(self):
        assert prioritize_tasks([]) == []

    def test_single_task_gets_order_1(self):
        result = prioritize_tasks(make_tasks({}))
        assert result[0]["recommended_order"] == 1


# ── summarize_plan ────────────────────────────────────────────────────────────

class TestSummarizePlan:
    def test_total_tasks_correct(self):
        tasks = make_tasks({}, {}, {})
        result = summarize_plan("test goal", tasks)
        assert result["total_tasks"] == 3

    def test_total_hours_correct(self):
        tasks = make_tasks({"estimated_minutes": 60}, {"estimated_minutes": 60})
        result = summarize_plan("test goal", tasks)
        assert result["total_hours"] == 2.0

    def test_priority_breakdown_correct(self):
        tasks = make_tasks(
            {"priority": "high"},
            {"priority": "high"},
            {"priority": "medium"},
            {"priority": "low"},
        )
        result = summarize_plan("test goal", tasks)
        assert result["priority_breakdown"]["high"] == 2
        assert result["priority_breakdown"]["medium"] == 1
        assert result["priority_breakdown"]["low"] == 1

    def test_first_task_title_included(self):
        tasks = make_tasks({"title": "First step"}, {"title": "Second step"})
        result = summarize_plan("test goal", tasks)
        assert result["first_task"] == "First step"

    def test_empty_tasks_first_task_is_none(self):
        result = summarize_plan("test goal", [])
        assert result["first_task"] is None

    def test_notes_passed_through(self):
        tasks = make_tasks({})
        result = summarize_plan("test goal", tasks, notes="some notes")
        assert result["notes"] == "some notes"

    def test_goal_included_in_result(self):
        tasks = make_tasks({})
        result = summarize_plan("my goal", tasks)
        assert result["goal"] == "my goal"
