from app.agents.planner import PlannerAgent
from app.agents.executor import ExecutorAgent


class Orchestrator:
    """
    Chains PlannerAgent → ExecutorAgent in sequence.
    Returns one clean dict that the /run endpoint and conversational flow can use.
    """

    def __init__(self):
        self.planner = PlannerAgent()
        self.executor = ExecutorAgent()

    def run(self, goal: str, context: str = "") -> dict:
        """
        Runs the two-step pipeline for a given goal.

        Step 1 — Planner: breaks the goal into a structured task list
        Step 2 — Executor: runs tools on the plan and gets AI insights
        """

        # ── Step 1: Plan ──────────────────────────────────────────────
        plan = self.planner.run(goal=goal, context=context)

        if "error" in plan:
            return self._error_response(
                f"Planner failed: {plan.get('error')}",
                plan.get("raw_response", "")
            )

        # ── Step 2: Execute ───────────────────────────────────────────
        execution_result = self.executor.run(plan=plan)

        if "error" in execution_result.get("ai_interpretation", {}):
            return self._error_response(
                "Executor failed to interpret tool results.",
                str(execution_result)
            )

        return self._build_response(plan, execution_result)

    def _build_response(self, plan: dict, execution_result: dict) -> dict:
        """
        Assembles the final response from both agents' outputs.
        """
        ai_interp = execution_result.get("ai_interpretation", {})
        tasks = plan.get("tasks", [])
        tool_insights = ai_interp.get("tool_insights", [])
        warnings = ai_interp.get("warnings", [])
        execution_results = tool_insights + (["WARNING: " + w for w in warnings] if warnings else [])

        return {
            "status": "ok",
            "plan": tasks,
            "execution_results": execution_results,
            "critique": "",
            "final_summary": ""
        }

    def _error_response(self, message: str, detail: str = "") -> dict:
        """
        Returns a safe error response that still matches AgentResponse shape.
        This prevents the API from crashing when something goes wrong.
        """
        return {
            "status": "error",
            "plan": [],
            "execution_results": [],
            "critique": "",
            "final_summary": f"Pipeline error: {message}\n{detail}".strip()
        }
