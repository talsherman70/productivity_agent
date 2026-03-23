from datetime import datetime


def validate_plan(tasks: list) -> dict:
    """
    Checks if a plan is valid and complete.
    Looks for missing fields, empty tasks, or bad priority values.
    """
    issues = []
    valid_priorities = {"high", "medium", "low"}

    if not tasks:
        return {"valid": False, "issues": ["Task list is empty"]}

    for task in tasks:
        task_id = task.get("id", "?")

        if not task.get("title"):
            issues.append(f"Task {task_id} is missing a title")

        if not task.get("description"):
            issues.append(f"Task {task_id} is missing a description")

        if task.get("priority") not in valid_priorities:
            issues.append(f"Task {task_id} has invalid priority: {task.get('priority')}")

        if not isinstance(task.get("estimated_minutes"), (int, float)):
            issues.append(f"Task {task_id} is missing a valid time estimate")

    return {
        "valid": len(issues) == 0,
        "issues": issues
    }


def detect_schedule_conflicts(tasks: list, available_minutes_per_day: int = 120) -> dict:
    """
    Checks if the total time of all tasks exceeds the daily available time.
    Flags tasks that push past the limit.
    """
    total_minutes = sum(task.get("estimated_minutes", 0) for task in tasks)
    over_budget = total_minutes > available_minutes_per_day

    overloaded_tasks = []
    running_total = 0

    for task in tasks:
        running_total += task.get("estimated_minutes", 0)
        if running_total > available_minutes_per_day:
            overloaded_tasks.append(task.get("title", f"Task {task.get('id')}"))

    return {
        "total_minutes": total_minutes,
        "available_minutes": available_minutes_per_day,
        "over_budget": over_budget,
        "overloaded_tasks": overloaded_tasks,
        "surplus_or_deficit": available_minutes_per_day - total_minutes
    }


def prioritize_tasks(tasks: list) -> list:
    """
    Sorts tasks by priority: high first, then medium, then low.
    Within the same priority, shorter tasks come first.
    """
    priority_order = {"high": 0, "medium": 1, "low": 2}

    sorted_tasks = sorted(
        tasks,
        key=lambda t: (
            priority_order.get(t.get("priority", "low"), 2),
            t.get("estimated_minutes", 0)
        )
    )

    # Add a position number to each task
    for i, task in enumerate(sorted_tasks, start=1):
        task["recommended_order"] = i

    return sorted_tasks


def summarize_plan(goal: str, tasks: list, notes: str = "") -> dict:
    """
    Creates a human-readable summary of the full plan.
    """
    total_minutes = sum(task.get("estimated_minutes", 0) for task in tasks)
    total_hours = round(total_minutes / 60, 1)

    high_priority = [t for t in tasks if t.get("priority") == "high"]
    medium_priority = [t for t in tasks if t.get("priority") == "medium"]
    low_priority = [t for t in tasks if t.get("priority") == "low"]

    return {
        "goal": goal,
        "total_tasks": len(tasks),
        "total_hours": total_hours,
        "priority_breakdown": {
            "high": len(high_priority),
            "medium": len(medium_priority),
            "low": len(low_priority)
        },
        "first_task": tasks[0].get("title") if tasks else None,
        "notes": notes
    }