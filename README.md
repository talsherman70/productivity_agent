# Productivity Agent

A multi-agent AI assistant for personal productivity — plan goals, manage your Google Calendar, find places, check the weather, and chat via WhatsApp.

Built with Python, FastAPI, and the Claude API (Anthropic).

---

## What it does

You send a message like _"Prepare for a Python job interview next week"_ and the assistant:

1. **Plans** — breaks the goal into a concrete task list with priorities and time estimates
2. **Executes** — runs analytical tools (conflict detection, prioritization, validation) and interprets the results
3. **Acts** — creates, deletes, or checks calendar events; searches for places; fetches weather; answers questions

The assistant is conversational and multi-turn — it maintains session history, asks clarifying questions when information is missing, and confirms before taking destructive actions like deleting events.

---

## Architecture

### Conversation flow

```
POST /chat
    │
    ▼
ConversationalOrchestrator
    │
    ├── Intent detection (Claude Sonnet) ──────────────────────────────────────────────┐
    │       Classifies message as one of:                                               │
    │       new_goal / create_event / delete_event / delete_range / replace_event /     │
    │       check_calendar / search_places / check_weather / confirmation / ...          │
    │                                                                                   │
    ├── Calendar handler ── Google Calendar API (create / delete / list / range-delete) │
    ├── Places handler ───── Google Places API (text search, nearby search, details)    │
    ├── Weather handler ──── wttr.in (free forecast API, no key needed)                │
    ├── Planning pipeline ── Planner → Executor (see below)                             │
    └── Conversational LLM ─ Claude Haiku (clarifying questions, general answers)      │
                                                                                        │
    Context injected into every planning request: ──────────────────────────────────────┘
        - Upcoming Google Calendar events
        - 3-day weather forecast
        - Jewish holidays & Shabbat times (Hebcal API)
```

### Planning pipeline (used for goal-based requests)

```
Orchestrator (coordinator.py)
    │
    ├── PlannerAgent     → breaks goal into tasks (JSON)
    │
    ├── ExecutorAgent    → runs tools, asks Claude to interpret
    │       ├── validate_plan
    │       ├── detect_schedule_conflicts
    │       ├── prioritize_tasks
    │       └── summarize_plan
    │
    └── CriticAgent      → scores and reviews the plan (currently unused in chat flow)
```

---

## Project structure

```
productivity_agent/
├── app/
│   ├── main.py                              # FastAPI app entry point
│   ├── static/
│   │   └── index.html                       # Web chat UI
│   ├── api/
│   │   ├── routes.py                        # /chat/new, /chat, /run, /health
│   │   └── whatsapp.py                      # Twilio WhatsApp webhook
│   ├── agents/
│   │   ├── planner.py                       # PlannerAgent — goal → task list
│   │   ├── executor.py                      # ExecutorAgent — tools + interpretation
│   │   └── critic.py                        # CriticAgent — scores plan 1–10
│   ├── tools/
│   │   └── productivity.py                  # validate_plan, detect_conflicts, prioritize, summarize
│   ├── orchestrator/
│   │   ├── coordinator.py                   # Chains Planner → Executor
│   │   └── conversational_orchestrator.py   # Multi-turn intent router (main entry point)
│   ├── core/
│   │   ├── llm_client.py                    # Anthropic SDK wrapper
│   │   ├── utils.py                         # parse_llm_json()
│   │   ├── conversation.py                  # ConversationHistory (per session)
│   │   ├── database.py                      # SQLAlchemy models (sessions, messages, phone mappings)
│   │   └── session_store.py                 # InMemory + SQLite session stores
│   └── services/
│       ├── calendar_service.py              # Google Calendar read/write
│       ├── weather_service.py               # wttr.in weather forecast
│       ├── places_service.py                # Google Places search
│       └── jewish_calendar_service.py       # Hebcal holidays & Shabbat times
├── tests/                                   # pytest suite (14 files)
├── data/
│   └── sessions.db                          # SQLite session store (auto-created)
├── setup_calendar.py                        # One-time Google OAuth flow
├── requirements.txt
├── .env                                     # API keys (never commit)
├── credentials.json                         # Google OAuth2 credentials (never commit)
└── token.json                               # Google auth token (auto-generated, never commit)
```

---

## Tech stack

| Technology | Purpose |
|---|---|
| Python 3.11+ | Core language |
| FastAPI | REST API framework |
| Uvicorn | ASGI server |
| Anthropic SDK | Claude API (Sonnet for intent, Haiku for conversation) |
| Google Calendar API | Create, read, delete events |
| Google Places API | Place search and details |
| wttr.in | Free weather forecast (no key needed) |
| Hebcal API | Jewish holidays and Shabbat times (no key needed) |
| SQLAlchemy + SQLite | Persistent session storage |
| Twilio | WhatsApp webhook integration |
| Pydantic | Request/response validation |

---

## Setup

### 1. Clone and install

```bash
git clone <your-repo-url>
cd productivity_agent
python -m venv .venv

# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_PLACES_API_KEY=AIzaSy...       # optional — enables place search
TWILIO_ACCOUNT_SID=AC...              # optional — enables WhatsApp
TWILIO_AUTH_TOKEN=...                 # optional — enables WhatsApp
```

### 3. Set up Google Calendar (optional)

1. Create a Google Cloud project and enable the Google Calendar API
2. Download OAuth2 credentials as `credentials.json` and place it in the project root
3. Run the auth script once to generate `token.json`:

```bash
python setup_calendar.py
```

### 4. Start the server

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` for the web chat UI, or `http://127.0.0.1:8000/docs` for the Swagger API explorer.

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Server health check |
| `POST` | `/chat/new` | Create a new session, returns `session_id` |
| `POST` | `/chat` | Send a message in an existing session |
| `POST` | `/run` | Legacy single-shot planning pipeline |
| `POST` | `/webhook/whatsapp` | Twilio WhatsApp webhook |

### Chat request

```json
POST /chat
{
  "session_id": "abc123",
  "message": "add yoga on Friday at 7am",
  "location": { "lat": 32.08, "lng": 34.78 }
}
```

### Chat response

```json
{
  "session_id": "abc123",
  "assistant_message": "Done — added Yoga on Fri May 01 at 07:00 to your calendar.",
  "structured_data": { "event": { ... } },
  "action": "event_created"
}
```

### Supported actions (in `action` field)

| Action | Triggered by |
|---|---|
| `event_created` | "add X on Y at Z" |
| `event_deleted` | "delete X" (after confirmation) |
| `delete_range_done` | "remove all yoga events this week" (after confirmation) |
| `delete_preview` | Preview shown before any delete |
| `replace_event` | "change X to Y at Z" |
| `calendar_shown` | "what's on my calendar?" |
| `places_shown` | "find an Italian restaurant near Tel Aviv" |
| `plan_delivered` | Goal-based planning request |
| `needs_context` | Missing info — agent asks a clarifying question |
| `cancelled` | User said no to a pending delete |

---

## Calendar features

- **Create event** — "add standup on Monday at 9am"
- **Delete event** — "delete my math test" (previews first, then confirms)
- **Delete range** — "remove all yoga events from May 1 to May 5" (filtered by title + date range, confirms before deleting)
- **Replace event** — "move yoga to Tuesday at 8am"
- **Check calendar** — "what do I have this week?"
- **Conflict detection** — warns if a new event overlaps an existing one
- **Timezone** — Asia/Jerusalem (UTC+3, Israel)

---

## WhatsApp

Point your Twilio sandbox webhook at:

```
POST https://<your-domain>/webhook/whatsapp
```

Each phone number gets a persistent session. Messages survive server restarts via SQLite.

---

## Key design decisions

- **No agent knows about the others** — each agent takes an input and returns a dict; only the orchestrator knows the order
- **Confirmation before destructive actions** — deletes always preview what will be removed and ask for confirmation
- **Context enrichment** — calendar events, weather, and Jewish holidays are injected into every planning request so Claude can avoid conflicts and respect constraints
- **Services are optional** — the server starts and runs even if Google Calendar, Places, or Twilio credentials are missing; those features are simply unavailable
- **Session persistence** — `SQLiteSessionStore` keeps conversation history across server restarts; `InMemorySessionStore` is available for testing
