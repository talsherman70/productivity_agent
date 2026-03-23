import json
from app.core.llm_client import LLMClient

PLANNER_SYSTEM_PROMPT = """
You are a productivity planner agent. Your job is to take a user's goal 
and break it down into a clear, actionable task list.

When given a goal, you must respond with ONLY a valid JSON object in this 
exact format, no extra text before or after:

{
    "goal": "the original goal",
    "tasks": [
        {
            "id": 1,
            "title": "short task title",
            "description": "what exactly to do",
            "estimated_minutes": 30,
            "priority": "high"
        }
    ],
    "total_estimated_minutes": 120,
    "notes": "any important observations about this plan"
}

Rules:
- priority must be one of: "high", "medium", "low"
- estimated_minutes must be a realistic number
- break the goal into 3 to 7 tasks maximum
- tasks should be in logical order
- be specific and practical, not vague
"""


class PlannerAgent:
    def __init__(self):
        self.llm = LLMClient()

    def run(self, goal: str, context: str = "") -> dict:
        """
        Takes a goal and returns a structured plan as a dictionary.
        """
        user_message = f"Goal: {goal}"

        if context:
            user_message += f"\nExtra context: {context}"

        raw_response = self.llm.chat(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_message=user_message
        )

        return self._parse_response(raw_response)

    def _parse_response(self, raw_response: str) -> dict:
        """
        Parses Claude's response into a Python dictionary.
        If parsing fails, returns an error dictionary instead of crashing.
        """
        try:
            # Remove markdown code blocks if Claude added them
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            return json.loads(cleaned.strip())
        except json.JSONDecodeError:
            return {
                "error": "Planner failed to return valid JSON",
                "raw_response": raw_response
            }