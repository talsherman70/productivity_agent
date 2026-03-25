from app.agents.planner import PlannerAgent
from app.agents.executor import ExecutorAgent
from app.agents.critic import CriticAgent


class Orchestrator:
    """
    Chains PlannerAgent → ExecutorAgent → CriticAgent in sequence.
    Each agent's output is passed as input to the next.
    Returns one clean dict that the /run endpoint can return directly.
    """

    def __init__(self):
        self.planner = PlannerAgent()
        self.executor = ExecutorAgent()
        self.critic = CriticAgent()

    def run(self, goal: str, context: str = "") -> dict:
        """
        Runs the full pipeline for a given goal.

        Step 1 — Planner: breaks the goal into a structured task list
        Step 2 — Executor: runs tools on the plan and gets AI insights
        Step 3 — Critic: reviews everything and scores the plan

        Returns a dict with keys matching AgentResponse in routes.py.
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

        # ── Step 3: Critique ──────────────────────────────────────────
        critic_result = self.critic.run(
            goal=goal,
            plan=plan,
            execution_result=execution_result
        )

        critique_data = critic_result.get("critique", {})

        if "error" in critique_data:
            return self._error_response(
                "Critic failed to review the plan.",
                str(critic_result)
            )

        # ── Build the final response ──────────────────────────────────
        return self._build_response(plan, execution_result, critique_data)

    def _build_response(self, plan: dict, execution_result: dict, critique: dict) -> dict:
        """
        Assembles the final response from all three agents' outputs.
        Maps data to the fields expected by AgentResponse in routes.py.
        """
        ai_interp = execution_result.get("ai_interpretation", {})
        tool_results = execution_result.get("tool_results", {})

        # Pull the task list for the 'plan' field
        tasks = plan.get("tasks", [])

        # Pull tool insights for 'execution_results'
        tool_insights = ai_interp.get("tool_insights", [])
        warnings = ai_interp.get("warnings", [])
        execution_results = tool_insights + (["WARNING: " + w for w in warnings] if warnings else [])

        # Pull the critic's one-sentence verdict for 'critique'
        final_verdict = critique.get("final_verdict", "No verdict provided.")
        score = critique.get("score")
        quality = critique.get("overall_quality", "")
        critique_str = f"[Score: {score}/10 | Quality: {quality}] {final_verdict}"

        # Build a readable final summary
        summary = tool_results.get("summary", {})
        interp_first_step = ai_interp.get("recommended_first_step", "")
        strengths = critique.get("strengths", [])
        issues = critique.get("issues", [])

        final_summary_parts = [
            f"Goal: {plan.get('goal', '')}",
            f"Tasks: {summary.get('total_tasks', len(tasks))} | "
            f"Estimated time: {summary.get('total_hours', '?')} hours",
        ]

        if interp_first_step:
            final_summary_parts.append(f"Start with: {interp_first_step}")

        if strengths:
            final_summary_parts.append("Strengths: " + "; ".join(strengths[:2]))

        if issues:
            top_issue = issues[0]
            final_summary_parts.append(
                f"Top issue ({top_issue.get('severity', '?')} severity): "
                f"{top_issue.get('description', '')} — "
                f"Fix: {top_issue.get('suggestion', '')}"
            )

        final_summary = "\n".join(final_summary_parts)

        return {
            "status": "ok",
            "plan": tasks,
            "execution_results": execution_results,
            "critique": critique_str,
            "final_summary": final_summary
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
