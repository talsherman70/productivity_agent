from app.core.llm_client import LLMClient
from app.core.conversation import ConversationHistory
from app.core.session_store import AbstractSessionStore, session_store as default_store
from app.core.utils import parse_llm_json
from app.orchestrator.coordinator import Orchestrator


# ── System prompts ────────────────────────────────────────────────────────────

INTENT_SYSTEM_PROMPT = """
You are a conversation router for a productivity assistant.

Read the conversation history and classify the user's latest message.

Respond with ONLY a valid JSON object — no extra text:
{
    "intent": "new_goal" | "confirmation" | "rejection" | "refinement" | "question" | "other",
    "goal": "the user's productivity goal if one exists anywhere in the conversation, otherwise empty string",
    "context": "any useful context from the conversation such as time constraints or preferences, otherwise empty string"
}

Intent definitions:
- new_goal: the user is describing a new task, goal, or project they want a plan for
- confirmation: the user is agreeing to proceed (yes, go ahead, sure, do it, ok, sounds good, etc.)
- rejection: the user is saying no, cancel, stop, or don't do that
- refinement: the user wants to change or adjust the current goal or plan
- question: the user is asking a question about the plan or the assistant
- other: greetings, thanks, unrelated messages

Always extract the most recent active goal from the full conversation history.
"""

CONVERSATIONAL_SYSTEM_PROMPT = """
You are a helpful productivity assistant. You help users plan, organize, and achieve their goals.

Be warm, clear, and concise. Do not use filler phrases like "Certainly!" or "Of course!".
Get straight to the point.

When a user describes a goal, ask for confirmation before building a full plan.
When a user says no or rejects something, acknowledge it briefly and ask what they'd like instead.
When asked a question, answer it directly.
"""


# ── Orchestrator ──────────────────────────────────────────────────────────────

class ConversationalOrchestrator:
    """
    Manages a multi-turn conversation with the user.

    On each request it:
    1. Loads the session history
    2. Adds the new user message
    3. Detects intent (what does the user want?)
    4. Routes to the right handler
    5. Saves the assistant reply back to history
    6. Returns the response

    The full Planner→Executor→Critic pipeline only runs when the user
    has described a goal AND explicitly confirmed they want to proceed.
    """

    def __init__(self, store: AbstractSessionStore = None):
        # Use the provided store, or fall back to the global singleton
        self.store = store or default_store
        self.llm = LLMClient()
        self.pipeline = Orchestrator()

    def run(self, session_id: str, user_message: str) -> dict:
        """
        Main entry point.
        Takes a session_id and the user's latest message.
        Returns a response dict.
        """
        history = self.store.get_history(session_id)
        if history is None:
            return {
                "session_id": session_id,
                "assistant_message": "Session not found. Start a new one with POST /chat/new.",
                "structured_data": None,
                "action": "error"
            }

        # Step 1: Add the user message to history
        history.add_user(user_message)

        # Step 2: Ask Claude to classify what the user wants
        intent_data = self._detect_intent(history)
        intent = intent_data.get("intent", "other")
        goal = intent_data.get("goal", "").strip()
        context = intent_data.get("context", "").strip()

        # Step 3: Route to the right handler
        if intent == "new_goal" and goal:
            response = self._handle_new_goal(goal)

        elif intent == "confirmation" and goal:
            response = self._handle_confirmation(goal, context)

        elif intent == "rejection":
            response = self._handle_rejection(history)

        elif intent == "refinement" and goal:
            response = self._handle_refinement(goal)

        else:
            # Covers: questions, greetings, refinement with no goal, other
            response = self._handle_other(history)

        # Step 4: Save the assistant reply into history
        history.add_assistant(response["assistant_message"])
        self.store.save_history(session_id, history)

        response["session_id"] = session_id
        return response

    # ── Intent detection ──────────────────────────────────────────────────────

    def _detect_intent(self, history: ConversationHistory) -> dict:
        """
        Sends the full conversation to Claude and asks it to classify intent.
        Returns a dict with 'intent', 'goal', and 'context'.
        Falls back to {"intent": "other"} if parsing fails.
        """
        raw = self.llm.chat_with_history(
            system_prompt=INTENT_SYSTEM_PROMPT,
            messages=history.get_messages()
        )
        result = parse_llm_json(raw)
        if "error" in result:
            return {"intent": "other", "goal": "", "context": ""}
        return result

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_new_goal(self, goal: str) -> dict:
        """
        User described a new goal.
        Ask for confirmation before running the expensive pipeline.
        """
        return {
            "assistant_message": (
                f"Got it! I'll build a full productivity plan for:\n\"{goal}\"\n\n"
                "Shall I go ahead? Reply 'yes' to proceed, or tell me if you'd like to adjust anything."
            ),
            "structured_data": None,
            "action": "awaiting_confirmation"
        }

    def _handle_confirmation(self, goal: str, context: str) -> dict:
        """
        User confirmed. Run the full Planner→Executor→Critic pipeline.
        This is the only place the pipeline is called from the chat flow.
        """
        result = self.pipeline.run(goal=goal, context=context)

        if result.get("status") == "error":
            return {
                "assistant_message": (
                    f"Something went wrong while building your plan.\n"
                    f"{result.get('final_summary', '')}"
                ),
                "structured_data": None,
                "action": "error"
            }

        tasks = result.get("plan", [])
        first_task = tasks[0].get("title", "") if tasks else ""
        critique = result.get("critique", "")

        lines = [f"Here's your plan — {len(tasks)} tasks ready to go."]
        if first_task:
            lines.append(f"Start with: {first_task}")
        lines.append("\nLet me know if you'd like to adjust anything.")

        return {
            "assistant_message": "\n".join(lines),
            "structured_data": {
                "plan": result.get("plan"),
                "execution_results": result.get("execution_results"),
                "critique": result.get("critique"),
                "final_summary": result.get("final_summary")
            },
            "action": "plan_delivered"
        }

    def _handle_rejection(self, history: ConversationHistory) -> dict:
        """
        User said no. Respond conversationally and ask what they'd like instead.
        """
        raw = self.llm.chat_with_history(
            system_prompt=CONVERSATIONAL_SYSTEM_PROMPT,
            messages=history.get_messages()
        )
        return {
            "assistant_message": raw,
            "structured_data": None,
            "action": "rejected"
        }

    def _handle_refinement(self, updated_goal: str) -> dict:
        """
        User wants to change the goal. Acknowledge and ask for confirmation again.
        """
        return {
            "assistant_message": (
                f"Got it, I'll adjust the goal to:\n\"{updated_goal}\"\n\n"
                "Shall I go ahead with this updated version?"
            ),
            "structured_data": None,
            "action": "awaiting_confirmation"
        }

    def _handle_other(self, history: ConversationHistory) -> dict:
        """
        Handles questions, greetings, and anything that doesn't fit the other categories.
        Just passes the full history to Claude and lets it respond naturally.
        """
        raw = self.llm.chat_with_history(
            system_prompt=CONVERSATIONAL_SYSTEM_PROMPT,
            messages=history.get_messages()
        )
        return {
            "assistant_message": raw,
            "structured_data": None,
            "action": "conversation"
        }
