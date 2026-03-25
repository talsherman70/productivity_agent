import json
from app.core.llm_client import LLMClient
from app.core.utils import parse_llm_json

CRITIC_SYSTEM_PROMPT = """
You are a critical review agent specializing in productivity planning.
Your job is to review a goal, a task plan, and the execution analysis,
then identify any problems, gaps, or risks.

You are not here to be encouraging — you are here to be honest and precise.

Respond with ONLY a valid JSON object in this exact format:
{
    "overall_quality": "good" or "acceptable" or "poor",
    "score": a number from 1 to 10,
    "strengths": [
        "specific strength 1",
        "specific strength 2"
    ],
    "issues": [
        {
            "severity": "high" or "medium" or "low",
            "description": "what the problem is",
            "suggestion": "how to fix it"
        }
    ],
    "missing_elements": [
        "something important that was not addressed"
    ],
    "final_verdict": "one sentence summary of whether this plan is ready to execute"
}

Be specific. Reference actual tasks and numbers from the plan.
Do not invent problems that do not exist.
If the plan is genuinely good, say so.
Be concise. Each issue description must be under 30 words.
Each suggestion must be under 20 words. Maximum 4 issues total.
"""


class CriticAgent:
    def __init__(self):
        self.llm = LLMClient()

    def run(self, goal: str, plan: dict, execution_result: dict) -> dict:
        """
        Reviews the full pipeline output and returns a critical assessment.

        goal: the original user goal
        plan: the planner's output
        execution_result: the executor's full output including tool results
        """
        ai_critique = self._critique(goal, plan, execution_result)

        return {
            "goal": goal,
            "critique": ai_critique
        }

    def _critique(self, goal: str, plan: dict, execution_result: dict) -> dict:
        """
        Sends the full context to Claude for critical review.
        """
        user_message = f"""
Please critically review this productivity plan.

Original goal: {goal}

Generated plan:
{json.dumps(plan, indent=2)}

Execution analysis:
{json.dumps(execution_result.get("ai_interpretation", {}), indent=2)}

Tool results summary:
- Plan valid: {execution_result.get("tool_results", {}).get("validation", {}).get("valid")}
- Over budget: {execution_result.get("tool_results", {}).get("conflicts", {}).get("over_budget")}
- Total minutes: {execution_result.get("tool_results", {}).get("conflicts", {}).get("total_minutes")}
- Available minutes: {execution_result.get("tool_results", {}).get("conflicts", {}).get("available_minutes")}
- Total tasks: {execution_result.get("tool_results", {}).get("summary", {}).get("total_tasks")}

Provide your critical review.
"""
        raw_response = self.llm.chat(
            system_prompt=CRITIC_SYSTEM_PROMPT,
            user_message=user_message
        )

        return self._parse_response(raw_response)

    def _parse_response(self, raw_response: str) -> dict:
        return parse_llm_json(raw_response)