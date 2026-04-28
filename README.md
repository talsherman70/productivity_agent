# Productivity Agent

A conversational AI assistant for personal productivity. Chat with it to plan goals, manage your Google Calendar, find places, and check the weather — via a web UI or WhatsApp.

Built with Python, FastAPI, and Claude (Anthropic).

---

## What it does

- **Goal planning** — describe a goal and get a structured task plan with priorities and time estimates
- **Calendar management** — create, delete, and reschedule events; bulk-delete by date range or title filter
- **Place search** — find restaurants, gyms, cafes, etc. via Google Places
- **Weather** — get a forecast for any location or date
- **WhatsApp support** — full chat experience via Twilio sandbox
- **Context-aware** — calendar events, weather, and Jewish holidays are automatically injected into planning so Claude avoids conflicts

---

## Architecture

```
User message
    │
    ▼
ConversationalOrchestrator
    ├── Intent detection (Claude Sonnet)
    ├── Calendar handler   ── Google Calendar API
    ├── Places handler     ── Google Places API
    ├── Weather handler    ── wttr.in (no key needed)
    └── Planning pipeline  ── Planner → Executor (Claude Opus)
```

---

## Project structure

```
productivity_agent/
├── app/
│   ├── main.py
│   ├── static/index.html                    # Web chat UI
│   ├── api/
│   │   ├── routes.py                        # /chat/new, /chat, /run, /health
│   │   └── whatsapp.py                      # Twilio WhatsApp webhook
│   ├── agents/
│   │   ├── planner.py                       # Goal → task list
│   │   ├── executor.py                      # Tools + plan interpretation
│   │   └── critic.py                        # Plan scoring
│   ├── orchestrator/
│   │   ├── coordinator.py                   # Planner → Executor chain
│   │   └── conversational_orchestrator.py   # Intent router (main entry point)
│   ├── core/
│   │   ├── llm_client.py                    # Anthropic SDK wrapper
│   │   ├── conversation.py                  # Per-session message history
│   │   └── session_store.py                 # SQLite-backed session persistence
│   └── services/
│       ├── calendar_service.py
│       ├── weather_service.py
│       ├── places_service.py
│       └── jewish_calendar_service.py       # Hebcal holidays & Shabbat times
├── setup_calendar.py                        # One-time Google OAuth flow
├── requirements.txt
└── .env                                     # API keys (never commit)
```

---

## Setup

```bash
git clone <your-repo-url>
cd productivity_agent
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file:

```env
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_PLACES_API_KEY=...    # optional
TWILIO_ACCOUNT_SID=...       # optional
TWILIO_AUTH_TOKEN=...        # optional
```

For Google Calendar, place `credentials.json` in the project root and run:

```bash
python setup_calendar.py
```

Then start the server:

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` for the chat UI.

---

## Notes

- All services (calendar, places, weather, WhatsApp) are optional — the server runs without them
- Sessions persist across restarts via SQLite
- Timezone is hardcoded to Asia/Jerusalem
