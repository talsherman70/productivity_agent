import json
from app.core.llm_client import LLMClient
from app.tools.productivity import (
    validate_plan,
    detect_schedule_conflicts,
    prioritize_tasks,
    summarize_plan
)

EXECUTOR_SYSTEM_PROMPT = """
You are a productivity execution agent. You receive a task plan and the 
results of running analytical tools on it.

Your job is to interpret these tool results and provide a clear, 
actionable execution report.

Respond with ONLY a valid JSON object in this exact format:
{
    "status": "ready" or "needs_adjustment",
    "tool_insights": [
        "insight 1 based on tool results",
        "insight 2 based on tool results"
    ],
    "recommended_first_step": "the very first thing the user should do",
    "warnings": ["any warnings based on conflicts or issues found"],
    "adjusted_plan_notes": "any suggestions to fix conflicts or issues"
}

Be specific and practical. Base everything on the tool results provided.
"""


class ExecutorAgent:
    def __init__(self):
        self.llm = LLMClient()

    def run(self, plan: dict, available_minutes_per_day: int = 120) -> dict:
        """
        Takes a plan from the Planner and enriches it by running tools
        and getting AI interpretation of the results.
        """
        tasks = plan.get("tasks", [])
        goal = plan.get("goal", "")
        notes = plan.get("notes", "")

        # Step 1: Run all tools
        tool_results = self._run_tools(tasks, goal, notes, available_minutes_per_day)

        # Step 2: Ask Claude to interpret the tool results
        ai_interpretation = self._interpret_results(goal, tool_results)

        # Step 3: Return everything combined
        return {
            "original_plan": plan,
            "tool_results": tool_results,
            "ai_interpretation": ai_interpretation
        }

    def _run_tools(self, tasks: list, goal: str, notes: str, available_minutes: int) -> dict:
        """
        Runs all tools against the task list and returns their results.
        """
        validation = validate_plan(tasks)
        conflicts = detect_schedule_conflicts(tasks, available_minutes)
        prioritized = prioritize_tasks(tasks.copy())
        summary = summarize_plan(goal, tasks, notes)

        return {
            "validation": validation,
            "conflicts": conflicts,
            "prioritized_tasks": prioritized,
            "summary": summary
        }

    def _interpret_results(self, goal: str, tool_results: dict) -> dict:
        """
        Sends tool results to Claude for interpretation and actionable insights.
        """
        user_message = f"""
Goal: {goal}

Tool Results:
{json.dumps(tool_results, indent=2)}

Based on these tool results, provide your execution report.
"""
        raw_response = self.llm.chat(
            system_prompt=EXECUTOR_SYSTEM_PROMPT,
            user_message=user_message
        )

        return self._parse_response(raw_response)

    def _parse_response(self, raw_response: str) -> dict:
        """
        Parses Claude's response, handling markdown code blocks if present.
        """
        try:
            cleaned = raw_response.strip()
            if "```" in cleaned:
                parts = cleaned.split("```")
                for part in parts:
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("{"):
                        cleaned = part
                        break
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {
                "error": "Executor failed to return valid JSON",
                "raw_response": raw_response
            }