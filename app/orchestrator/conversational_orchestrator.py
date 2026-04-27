from datetime import datetime
from app.core.llm_client import LLMClient
from app.core.conversation import ConversationHistory
from app.core.session_store import AbstractSessionStore, session_store as default_store
from app.core.utils import parse_llm_json
from app.orchestrator.coordinator import Orchestrator


# ── System prompts ────────────────────────────────────────────────────────────

def get_intent_system_prompt() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return f"""
You are a conversation router for a productivity assistant with Google Calendar and Google Places access.

Read the conversation history and classify the user's latest message.

Respond with ONLY a valid JSON object — no extra text:
{{
    "intent": "new_goal" | "needs_context" | "confirmation" | "rejection" | "refinement" | "create_event" | "delete_event" | "check_calendar" | "search_places" | "select_place" | "ask_distances" | "check_weather" | "question" | "other",
    "goal": "the user's productivity goal if one exists, otherwise empty string",
    "context": "any useful context from the full conversation (preferences, constraints, answers), otherwise empty string",
    "calendar_event": {{
        "title": "event title",
        "date": "YYYY-MM-DD",
        "time": "HH:MM",
        "duration_minutes": 60
    }},
    "delete_query": {{
        "title": "partial or full title of the event to delete",
        "date": "YYYY-MM-DD or empty string if not specified"
    }},
    "weather_query": {{
        "location": "city or area to check weather for",
        "date": "YYYY-MM-DD for a specific day, or empty string for full forecast"
    }},
    "places_query": {{
        "query": "what the user is looking for (e.g. Italian restaurant)",
        "location": "where to search (e.g. Tel Aviv) — empty string if not specified",
        "nearby": false,
        "radius_meters": 2000
    }},
    "selected_place_index": null
}}

Intent definitions:
- new_goal: user described a productivity goal with enough context to build a plan
- needs_context: user wants something done but key info is missing — ask ONE question
- confirmation: user is agreeing to proceed (yes, go ahead, sure, ok, etc.)
- rejection: user is saying no, cancel, or stop
- refinement: user wants to change or adjust the current goal or plan
- create_event: user wants to add something to their calendar AND you have title + date + time
- check_calendar: user wants to see what is on their calendar
- search_places: user wants to find a place (restaurant, cafe, gym, etc.)
- select_place: user is picking one of the places shown in the previous assistant message (e.g. "the first one", "number 2", "add that to my calendar")
- delete_event: user wants to remove an event from their calendar
- check_weather: user wants to know the weather for a location or date
- ask_distances: user is asking how far the listed places are (e.g. "how far are they?", "what are the distances?", "which is closest?")
- question: user is asking a general question
- other: greetings, thanks, unrelated messages

Rules:
- Use needs_context if the user wants to create a calendar event but date or time is missing
- Only use create_event when you have title, date, AND time
- Use search_places when the user wants to find any kind of place or venue
- Set nearby=true and populate location when the user says "near me" or gives a specific area
- Set radius_meters based on what the user specifies (e.g. "2 km" → 2000, "500 m" → 500); default 2000
- Use select_place when the user refers to a place from the previous list (e.g. "book the second one", "add it to my calendar")
- selected_place_index is 0-based (first = 0, second = 1, etc.), null if not applicable
- The calendar_event field is only required when intent is create_event, otherwise omit it or leave it empty
- Convert relative dates to absolute dates (today is {today})
- Always output times in LOCAL 24-hour format — do NOT convert to UTC (e.g. "5pm" → "17:00", "9am" → "09:00")
- duration_minutes defaults to 60 if not specified

Always accumulate context from the full conversation history.
""".strip()


CONVERSATIONAL_SYSTEM_PROMPT = """
You are a helpful personal assistant. You help users plan, organise, and manage their time.
You are connected to the user's Google Calendar and Google Places.
You can read events, create events, delete events, and search for places.

Be warm, clear, and concise. Do not use filler phrases like "Certainly!" or "Of course!".
Get straight to the point.

When you need more information, ask ONE specific question at a time.
Never ask multiple questions at once.
When a user says no or rejects something, acknowledge it briefly and ask what they'd like instead.
When asked a question, answer it directly.
""".strip()


# ── Orchestrator ──────────────────────────────────────────────────────────────

class ConversationalOrchestrator:
    def __init__(self, store: AbstractSessionStore = None):
        self.store = store or default_store
        self.llm = LLMClient(model="claude-haiku-4-5-20251001")
        self.fast_llm = LLMClient(model="claude-haiku-4-5-20251001")
        self.pipeline = Orchestrator()

        from app.services.calendar_service import calendar_service
        self.calendar = calendar_service

        from app.services.places_service import places_service
        self.places = places_service

        from app.services.weather_service import weather_service
        self.weather = weather_service

        from app.services.jewish_calendar_service import jewish_calendar_service
        self.jewish_calendar = jewish_calendar_service

    def run(self, session_id: str, user_message: str, location: dict = None) -> dict:
        history = self.store.get_history(session_id)
        if history is None:
            return {
                "session_id": session_id,
                "assistant_message": "Session not found. Start a new one with POST /chat/new.",
                "structured_data": None,
                "action": "error"
            }

        history.add_user(user_message)

        # Store latest location on the instance for use by handlers
        if location:
            self._user_location = location

        intent_data = self._detect_intent(history)
        intent = intent_data.get("intent", "other")
        goal = intent_data.get("goal", "").strip()
        context = intent_data.get("context", "").strip()
        calendar_event = intent_data.get("calendar_event", {})
        delete_query = intent_data.get("delete_query", {})
        weather_query = intent_data.get("weather_query", {})
        places_query = intent_data.get("places_query", {})
        selected_index = intent_data.get("selected_place_index")

        # ── Route ─────────────────────────────────────────────────────────────
        if intent in ("new_goal", "confirmation", "refinement") and goal:
            response = self._handle_pipeline(goal, context)

        elif intent == "create_event" and calendar_event:
            response = self._handle_create_event(calendar_event)

        elif intent == "delete_event":
            response = self._handle_delete_event(delete_query)

        elif intent == "check_calendar":
            response = self._handle_check_calendar()

        elif intent == "search_places" and places_query:
            response = self._handle_search_places(places_query)

        elif intent == "select_place":
            response = self._handle_select_place(history, selected_index, calendar_event)

        elif intent == "ask_distances":
            response = self._handle_ask_distances()

        elif intent == "check_weather":
            response = self._handle_check_weather(weather_query)

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
            return {"intent": "other", "goal": "", "context": "", "calendar_event": {}, "places_query": {}}
        return result

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_pipeline(self, goal: str, context: str) -> dict:
        full_context = context

        if self.calendar:
            try:
                events = self.calendar.get_upcoming_events(days=14)
                if events:
                    calendar_context = self.calendar.format_events_for_context(events)
                    full_context = f"{context}\n\nUpcoming calendar events:\n{calendar_context}".strip()
            except Exception:
                pass

        if self.weather:
            try:
                loc = getattr(self, "_user_location", None)
                weather_location = f"{loc['lat']},{loc['lng']}" if loc else "Tel Aviv"
                forecast = self.weather.get_forecast(weather_location, days=3)
                if forecast:
                    weather_context = self.weather.format_forecast(forecast)
                    full_context = f"{full_context}\n\nWeather forecast (next 3 days):\n{weather_context}".strip()
            except Exception:
                pass

        if self.jewish_calendar:
            try:
                from datetime import date, timedelta
                today = date.today().isoformat()
                two_weeks = (date.today() + timedelta(days=14)).isoformat()
                jewish_context = self.jewish_calendar.format_for_planner(today, two_weeks)
                if jewish_context:
                    full_context = f"{full_context}\n\nJewish calendar constraints (next 14 days):\n{jewish_context}".strip()
            except Exception:
                pass

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
        description = calendar_event.get("description", "")

        if not date or not time:
            return {
                "assistant_message": "I need a date and time to add this to your calendar. When would you like it?",
                "structured_data": None,
                "action": "needs_context"
            }

        try:
            conflicts = self.calendar.check_conflicts(date, time, duration)
            if conflicts:
                conflict_title = conflicts[0].get("summary", "something else")
                # If the conflict is the same event title we're trying to create,
                # it was already added — avoid an infinite loop.
                if conflict_title.lower() == title.lower():
                    return {
                        "assistant_message": f"\"{title}\" is already on your calendar at {time} on {date}. Did you want to change the time or add something else?",
                        "structured_data": None,
                        "action": "conflict_detected"
                    }
                return {
                    "assistant_message": f"You already have \"{conflict_title}\" at that time. Want to pick a different slot?",
                    "structured_data": None,
                    "action": "conflict_detected"
                }

            created = self.calendar.create_event(title, date, time, duration, description)
            confirmation = self.calendar.format_event_confirmation(created)

            return {
                "assistant_message": f"Done! Added {confirmation} to your calendar.",
                "structured_data": {"event": created},
                "action": "event_created"
            }

        except Exception:
            return {
                "assistant_message": "Something went wrong with the calendar. Try again?",
                "structured_data": None,
                "action": "error"
            }

    def _handle_check_calendar(self) -> dict:
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

    def _handle_search_places(self, places_query: dict) -> dict:
        if not self.places:
            return {
                "assistant_message": "Places search isn't available. Check your GOOGLE_PLACES_API_KEY.",
                "structured_data": None,
                "action": "places_unavailable"
            }

        query = places_query.get("query", "")
        location = places_query.get("location", "")
        nearby = places_query.get("nearby", False)
        radius = places_query.get("radius_meters", 2000)

        if not query:
            return {
                "assistant_message": "What kind of place are you looking for?",
                "structured_data": None,
                "action": "needs_context"
            }

        try:
            if nearby and location:
                results = self.places.nearby_search(location=location, query=query, radius=radius)
            else:
                search_query = f"{query} {location}".strip()
                results = self.places.text_search(query=search_query)

            if not results:
                return {
                    "assistant_message": f"No results found for \"{query}\". Try a different search?",
                    "structured_data": {"places": []},
                    "action": "places_shown"
                }

            formatted = self.places.format_places_for_context(results)
            self._last_places = results  # cache for select_place turn
            return {
                "assistant_message": f"Here's what I found:\n\n{formatted}\n\nWant to add one of these to your calendar?",
                "structured_data": {"places": results},
                "action": "places_shown"
            }

        except Exception as e:
            return {
                "assistant_message": "Couldn't complete the search right now. Try again?",
                "structured_data": None,
                "action": "error"
            }

    def _handle_select_place(
        self,
        history: ConversationHistory,
        selected_index,
        calendar_event: dict,
    ) -> dict:
        """
        User picked a place from the previous list.
        If we have date + time from the same message, create the event immediately.
        Otherwise ask when they'd like to go.
        """
        # Pull stored places from the last places_shown action
        places = self._get_last_places(history)

        if not places:
            return self._handle_other(history)

        try:
            index = int(selected_index) if selected_index is not None else 0
        except (TypeError, ValueError):
            index = 0

        if index >= len(places):
            index = 0

        place = places[index]

        # Enrich with details (website, phone) if we have a place_id
        place_id = place.get("place_id")
        if place_id:
            try:
                details = self.places.get_place_details(place_id)
                place = {**place, **details}  # merge, details take precedence
            except Exception:
                pass

        name, description = self.places.format_place_for_event(place)
        website = place.get("website", "")

        # If we already have date + time, create the event straight away
        date = calendar_event.get("date", "") if calendar_event else ""
        time = calendar_event.get("time", "") if calendar_event else ""
        duration = calendar_event.get("duration_minutes", 60) if calendar_event else 60

        if date and time:
            event_data = {
                "title": name,
                "date": date,
                "time": time,
                "duration_minutes": duration,
                "description": description,
            }
            response = self._handle_create_event(event_data)
            if website and response.get("action") == "event_created":
                response["assistant_message"] += f"\n\nBooking / more info: {website}"
            return response

        # No time yet — confirm the place, show booking link, and ask when
        address = place.get("formatted_address") or place.get("vicinity", "")
        address_str = f" ({address})" if address else ""
        website_str = f"\n\nBooking / more info: {website}" if website else ""
        return {
            "assistant_message": f"When would you like to go to {name}{address_str}?{website_str}",
            "structured_data": {"selected_place": place},
            "action": "place_selected"
        }

    def _get_last_places(self, history: ConversationHistory) -> list:
        """
        Walks back through conversation messages to find the most recent
        places list. We store them in structured_data but history only holds
        text — so we re-parse from the assistant message if needed.
        """
        # The places are not stored in ConversationHistory (text only),
        # so we re-run a minimal search using context from history.
        # As a simpler approach: store places on the instance between turns.
        return getattr(self, "_last_places", [])

    def _handle_delete_event(self, delete_query: dict) -> dict:
        if not self.calendar:
            return {
                "assistant_message": "Calendar isn't connected yet.",
                "structured_data": None,
                "action": "calendar_unavailable"
            }

        title_query = delete_query.get("title", "").lower().strip()
        date_query = delete_query.get("date", "").strip()

        if not title_query:
            return {
                "assistant_message": "Which event would you like to delete?",
                "structured_data": None,
                "action": "needs_context"
            }

        try:
            events = self.calendar.get_upcoming_events(days=30)
            words = [w for w in title_query.split() if len(w) > 2]
            matches = [
                e for e in events
                if all(w in e.get("summary", "").lower() for w in words)
                and (not date_query or date_query in e.get("start", {}).get("dateTime", ""))
            ]

            if not matches:
                return {
                    "assistant_message": f"I couldn't find any upcoming event matching \"{delete_query.get('title')}\". Want me to show your calendar?",
                    "structured_data": None,
                    "action": "not_found"
                }

            if len(matches) == 1:
                event = matches[0]
                self.calendar.delete_event(event["id"])
                confirmation = self.calendar.format_event_confirmation(event)
                return {
                    "assistant_message": f"Done — removed {confirmation} from your calendar.",
                    "structured_data": {"deleted_event": event},
                    "action": "event_deleted"
                }

            # Multiple matches — list them and ask which one
            formatted = self.calendar.format_events_for_context(matches)
            return {
                "assistant_message": f"I found a few matching events:\n\n{formatted}\n\nWhich one would you like to delete?",
                "structured_data": {"matches": matches},
                "action": "needs_context"
            }

        except Exception:
            return {
                "assistant_message": "Something went wrong with the calendar. Try again?",
                "structured_data": None,
                "action": "error"
            }

    def _handle_check_weather(self, weather_query: dict) -> dict:
        if not self.weather:
            return {
                "assistant_message": "Weather service isn't available right now.",
                "structured_data": None,
                "action": "error"
            }

        location = weather_query.get("location", "").strip()
        target_date = weather_query.get("date", "").strip()

        if not location:
            user_loc = getattr(self, "_user_location", None)
            if user_loc:
                location = f"{user_loc['lat']},{user_loc['lng']}"
            else:
                return {
                    "assistant_message": "Which city or area would you like the weather for?",
                    "structured_data": None,
                    "action": "needs_context"
                }

        try:
            if target_date:
                day = self.weather.get_weather_for_date(location, target_date)
                if not day:
                    return {
                        "assistant_message": f"I can only forecast up to 16 days ahead. {target_date} is out of range.",
                        "structured_data": None,
                        "action": "weather_shown"
                    }
                formatted = self.weather.format_single_day(day)
                warning = " You might want to plan for that." if self.weather.is_bad_weather(day) else ""
                return {
                    "assistant_message": f"Weather on that day:\n{formatted}{warning}",
                    "structured_data": {"weather": day},
                    "action": "weather_shown"
                }
            else:
                forecast = self.weather.get_forecast(location, days=7)
                formatted = self.weather.format_forecast(forecast)
                return {
                    "assistant_message": f"Weather for the next 3 days:\n\n{formatted}",
                    "structured_data": {"forecast": forecast},
                    "action": "weather_shown"
                }

        except ValueError as e:
            return {
                "assistant_message": f"Couldn't find weather for \"{location}\". Try a city name.",
                "structured_data": None,
                "action": "error"
            }
        except Exception:
            return {
                "assistant_message": "Couldn't fetch the weather right now. Try again?",
                "structured_data": None,
                "action": "error"
            }

    def _handle_ask_distances(self) -> dict:
        places = getattr(self, "_last_places", [])
        if not places:
            return {
                "assistant_message": "I don't have a list of places to show distances for. Try searching first.",
                "structured_data": None,
                "action": "conversation"
            }
        formatted = self.places.format_places_for_context(places, include_distances=True)
        return {
            "assistant_message": f"Here are the straight-line distances from your search location:\n\n{formatted}",
            "structured_data": {"places": places},
            "action": "distances_shown"
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
