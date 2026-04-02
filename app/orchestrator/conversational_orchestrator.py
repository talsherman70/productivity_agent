from datetime import datetime
from app.core.llm_client import LLMClient
from app.core.conversation import ConversationHistory
from app.core.session_store import AbstractSessionStore, session_store as default_store
from app.core.utils import parse_llm_json
from app.orchestrator.coordinator import Orchestrator


# ── System prompts ────────────────────────────────────────────────────────────

def get_intent_system_prompt() -> str:
    """
    Returns the intent detection prompt with today's date injected.
    This allows the model to correctly parse relative dates like 'tomorrow'.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    return f"""
You are a conversation router for a productivity assistant with Google Calendar access.

Read the conversation history and classify the user's latest message.

Respond with ONLY a valid JSON object — no extra text:
{{
    "intent": "new_goal" | "needs_context" | "confirmation" | "rejection" | "refinement" | "create_event" | "check_calendar" | "question" | "other",
    "goal": "the user's productivity goal if one exists, otherwise empty string",
    "context": "any useful context from the full conversation (preferences, constraints, answers), otherwise empty string",
    "calendar_event": {{
        "title": "event title",
        "date": "YYYY-MM-DD",
        "time": "HH:MM",
        "duration_minutes": 60
    }}
}}

Intent definitions:
- new_goal: user described a goal with enough context to build a plan
- needs_context: user wants something done but key info is missing — ask ONE question
- confirmation: user is agreeing to proceed (yes, go ahead, sure, ok, etc.)
- rejection: user is saying no, cancel, or stop
- refinement: user wants to change or adjust the current goal or plan
- create_event: user wants to add something to their calendar AND you have title + date + time
- check_calendar: user wants to see what is on their calendar
- question: user is asking a question
- other: greetings, thanks, unrelated messages

Rules:
- Use needs_context if the user wants to create a calendar event but date or time is missing
- Only use create_event when you have title, date, AND time
- The calendar_event field is only required when intent is create_event, otherwise omit it or leave it empty
- Convert relative dates to absolute dates (today is {today})
- duration_minutes defaults to 60 if not specified

Always accumulate context from the full conversation history.
""".strip()


CONVERSATIONAL_SYSTEM_PROMPT = """
You are a helpful personal assistant. You help users plan, organise, and manage their time.

Be warm, clear, and concise. Do not use filler phrases like "Certainly!" or "Of course!".
Get straight to the point.

When you need more information, ask ONE specific question at a time.
Never ask multiple questions at once.
When a user says no or rejects something, acknowledge it briefly and ask what they'd like instead.
When asked a question, answer it directly.
""".strip()


# ── Orchestrator ──────────────────────────────────────────────────────────────

class ConversationalOrchestrator:
    """
    Manages a multi-turn conversation with the user.

    On each request:
    1. Loads the session history
    2. Adds the new user message
    3. Detects intent
    4. Routes to the right handler (pipeline, calendar, or conversation)
    5. Saves the assistant reply back to history
    6. Returns the response
    """

    def __init__(self, store: AbstractSessionStore = None):
        self.store = store or default_store
        self.llm = LLMClient(model="claude-haiku-4-5-20251001")
        self.fast_llm = LLMClient(model="claude-haiku-4-5-20251001")
        self.pipeline = Orchestrator()

        # Use the shared singleton — already authenticated at server startup
        from app.services.calendar_service import calendar_service
        self.calendar = calendar_service

    def run(self, session_id: str, user_message: str) -> dict:
        history = self.store.get_history(session_id)
        if history is None:
            return {
                "session_id": session_id,
                "assistant_message": "Session not found. Start a new one with POST /chat/new.",
                "structured_data": None,
                "action": "error"
            }

        history.add_user(user_message)

        intent_data = self._detect_intent(history)
        intent = intent_data.get("intent", "other")
        goal = intent_data.get("goal", "").strip()
        context = intent_data.get("context", "").strip()
        calendar_event = intent_data.get("calendar_event", {})

        # ── Route ─────────────────────────────────────────────────────────────
        if intent in ("new_goal", "confirmation", "refinement") and goal:
            response = self._handle_pipeline(goal, context)

        elif intent == "create_event" and calendar_event:
            response = self._handle_create_event(calendar_event)

        elif intent == "check_calendar":
            response = self._handle_check_calendar()

        elif intent == "needs_context":
            response = self._handle_other(history)

        elif intent == "rejection":
            response = self._handle_rejection(history)

        else:
            response = self._handle_other(history)

        history.add_assistant(response["assistant_message"])
        self.store.save_history(session_id, history)

        response["session_id"] = session_id
        return response

    # ── Intent detection ──────────────────────────────────────────────────────

    def _detect_intent(self, history: ConversationHistory) -> dict:
        raw = self.fast_llm.chat_with_history(
            system_prompt=get_intent_system_prompt(),
            messages=history.get_messages()
        )
        result = parse_llm_json(raw)
        if "error" in result:
            return {"intent": "other", "goal": "", "context": "", "calendar_event": {}}
        return result

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_pipeline(self, goal: str, context: str) -> dict:
        """
        Runs Planner → Executor. Passes upcoming calendar events as context
        so the planner can schedule around existing commitments.
        """
        full_context = context

        if self.calendar:
            try:
                events = self.calendar.get_upcoming_events(days=14)
                if events:
                    calendar_context = self.calendar.format_events_for_context(events)
                    full_context = f"{context}\n\nUpcoming calendar events:\n{calendar_context}".strip()
            except Exception:
                pass  # Calendar read failed — proceed without it

        result = self.pipeline.run(goal=goal, context=full_context)

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

    def _handle_create_event(self, calendar_event: dict) -> dict:
        """
        Creates a Google Calendar event.
        Checks for conflicts first — if the slot is busy, tells the user instead of creating.
        """
        if not self.calendar:
            return {
                "assistant_message": "Calendar isn't connected yet. Set up credentials.json to enable this.",
                "structured_data": None,
                "action": "calendar_unavailable"
            }

        title = calendar_event.get("title", "Event")
        date = calendar_event.get("date", "")
        time = calendar_event.get("time", "")
        duration = calendar_event.get("duration_minutes", 60)

        if not date or not time:
            return {
                "assistant_message": "I need a date and time to add this to your calendar. When would you like it?",
                "structured_data": None,
                "action": "needs_context"
            }

        try:
            # Check for conflicts before creating
            conflicts = self.calendar.check_conflicts(date, time, duration)
            if conflicts:
                conflict_title = conflicts[0].get("summary", "something else")
                return {
                    "assistant_message": f"You already have \"{conflict_title}\" at that time. Want to pick a different slot?",
                    "structured_data": None,
                    "action": "conflict_detected"
                }

            # No conflicts — create the event
            created = self.calendar.create_event(title, date, time, duration)
            confirmation = self.calendar.format_event_confirmation(created)

            return {
                "assistant_message": f"Done! Added {confirmation} to your calendar.",
                "structured_data": {"event": created},
                "action": "event_created"
            }

        except Exception as e:
            return {
                "assistant_message": "Something went wrong with the calendar. Try again?",
                "structured_data": None,
                "action": "error"
            }

    def _handle_check_calendar(self) -> dict:
        """
        Fetches and displays upcoming events.
        """
        if not self.calendar:
            return {
                "assistant_message": "Calendar isn't connected yet. Set up credentials.json to enable this.",
                "structured_data": None,
                "action": "calendar_unavailable"
            }

        try:
            events = self.calendar.get_upcoming_events(days=7)
            if not events:
                return {
                    "assistant_message": "Nothing on your calendar in the next 7 days.",
                    "structured_data": {"events": []},
                    "action": "calendar_shown"
                }

            formatted = self.calendar.format_events_for_context(events)
            return {
                "assistant_message": f"Here's what you have coming up:\n\n{formatted}",
                "structured_data": {"events": events},
                "action": "calendar_shown"
            }

        except Exception:
            return {
                "assistant_message": "Couldn't read your calendar right now. Try again?",
                "structured_data": None,
                "action": "error"
            }

    def _handle_rejection(self, history: ConversationHistory) -> dict:
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
        raw = self.llm.chat_with_history(
            system_prompt=CONVERSATIONAL_SYSTEM_PROMPT,
            messages=history.get_messages()
        )
        return {
            "assistant_message": raw,
            "structured_data": None,
            "action": "conversation"
        }
