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
    "intent": "new_goal" | "needs_context" | "confirmation" | "rejection" | "refinement" | "question" | "other",
    "goal": "the user's productivity goal if one exists anywhere in the conversation, otherwise empty string",
    "context": "any useful context gathered from the full conversation (preferences, constraints, answers to questions), otherwise empty string"
}

Intent definitions:
- new_goal: the user described a goal AND you have enough context to act on it (e.g. planning a study schedule with a deadline)
- needs_context: the user wants something done but key information is missing before you can help (e.g. booking a restaurant without knowing cuisine, people count, or area — you need to ask)
- confirmation: the user is agreeing to proceed (yes, go ahead, sure, do it, ok, sounds good, etc.)
- rejection: the user is saying no, cancel, stop, or don't do that
- refinement: the user wants to change or adjust the current goal or plan
- question: the user is asking a question about the plan or the assistant
- other: greetings, thanks, unrelated messages

Key rule: if the user wants to BOOK, SCHEDULE, FIND, or DO something in the real world and you are missing
key details (what type, how many people, where, when, preferences), classify as needs_context, not new_goal.
Only classify as new_goal when you have enough to actually help.

Always extract the most recent active goal and accumulate context from the full conversation history.
"""

CONVERSATIONAL_SYSTEM_PROMPT = """
You are a helpful productivity assistant. You help users plan, organize, and achieve their goals.

Be warm, clear, and concise. Do not use filler phrases like "Certainly!" or "Of course!".
Get straight to the point.

When you need more information before you can help, ask ONE specific question at a time.
Never ask multiple questions at once. Wait for the answer before asking the next one.
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
        # Haiku for everything conversational — fast, feels instant
        self.llm = LLMClient(model="claude-haiku-4-5-20251001")
        # Also Haiku for intent detection
        self.fast_llm = LLMClient(model="claude-haiku-4-5-20251001")
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
        if intent in ("new_goal", "confirmation") and goal:
            # Have enough context — run the pipeline immediately
            response = self._handle_pipeline(goal, context)

        elif intent == "needs_context":
            # Missing key info — ask one clarifying question
            response = self._handle_other(history)

        elif intent == "rejection":
            response = self._handle_rejection(history)

        elif intent == "refinement" and goal:
            # Treat refinement as a new pipeline run with the updated goal
            response = self._handle_pipeline(goal, context)

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
        raw = self.fast_llm.chat_with_history(
            system_prompt=INTENT_SYSTEM_PROMPT,
            messages=history.get_messages()
        )
        result = parse_llm_json(raw)
        if "error" in result:
            return {"intent": "other", "goal": "", "context": ""}
        return result

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_pipeline(self, goal: str, context: str) -> dict:
        """
        Runs the Planner → Executor pipeline and returns a clean numbered list response.
        Called for new goals, confirmations, and refinements.
        """
        result = self.pipeline.run(goal=goal, context=context)

        if result.get("status") == "error":
            return {
                "assistant_message": "Something went wrong building your plan. Try again?",
                "structured_data": None,
                "action": "error"
            }

        tasks = result.get("plan", [])
        numbered = "\n".join(f"{i+1}. {t.get('title', '')}" for i, t in enumerate(tasks))
        message = f"Here's what I came up with:\n\n{numbered}"

        return {
            "assistant_message": message,
            "structured_data": {
                "plan": tasks,
                "execution_results": result.get("execution_results"),
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
