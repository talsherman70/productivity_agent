# Productivity Agent

A multi-agent AI assistant that takes a user's productivity goal and returns a structured, reviewed, and scored action plan.

Built as a portfolio project using Python, FastAPI, and the Claude API (Anthropic).

---

## What it does

You send a goal like _"Prepare for a Python job interview next week"_ and the system:

1. **Plans** — breaks the goal into a concrete task list with priorities and time estimates
2. **Executes** — runs analytical tools (conflict detection, prioritization, validation) and interprets the results
3. **Critiques** — scores the plan out of 10, lists strengths and issues, and gives a one-sentence final verdict

All three steps are chained automatically by an Orchestrator.

---

## Architecture

```
POST /run
    │
    ▼
Orchestrator (coordinator.py)
    │
    ├── PlannerAgent     → asks Claude to break the goal into tasks (JSON)
    │
    ├── ExecutorAgent    → runs 4 tools on the plan, asks Claude to interpret results
    │       ├── validate_plan
    │       ├── detect_schedule_conflicts
    │       ├── prioritize_tasks
    │       └── summarize_plan
    │
    └── CriticAgent      → asks Claude to score and review the full pipeline output
```

Each agent talks to Claude via `LLMClient`, a thin wrapper around the Anthropic SDK.
All agents share `parse_llm_json()` from `app/core/utils.py` to safely parse Claude's JSON responses.

---

## Project structure

```
productivity_agent/
├── app/
│   ├── main.py                     # FastAPI app entry point
│   ├── api/
│   │   └── routes.py               # /run and /health endpoints
│   ├── agents/
│   │   ├── planner.py              # PlannerAgent
│   │   ├── executor.py             # ExecutorAgent
│   │   └── critic.py               # CriticAgent
│   ├── tools/
│   │   └── productivity.py         # validate_plan, detect_schedule_conflicts, etc.
│   ├── orchestrator/
│   │   └── coordinator.py          # Chains all agents in sequence
│   └── core/
│       ├── llm_client.py           # Anthropic API wrapper
│       └── utils.py                # Shared JSON parser
├── requirements.txt
├── .env                            # Your API key goes here (never commit this)
└── README.md
```

---

## Tech stack

| Technology | Purpose |
|---|---|
| Python 3.11+ | Core language |
| FastAPI | REST API framework |
| Uvicorn | ASGI server |
| Anthropic SDK | Claude API client |
| Pydantic | Request/response validation |
| python-dotenv | Loads `.env` file |

---

## Setup

### 1. Clone the repo

```bash
git clone <your-repo-url>
cd productivity_agent
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac/Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Add your API key

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=your_key_here
```

Get your key at [console.anthropic.com](https://console.anthropic.com).

### 5. Start the server

```bash
uvicorn app.main:app --reload
```

---

## Usage

Open `http://127.0.0.1:8000/docs` in your browser.

Use the **POST /run** endpoint with a JSON body:

```json
{
  "goal": "Prepare for a Python job interview next week",
  "context": "I have 2 hours per day available"
}
```

### Example response

```json
{
  "status": "ok",
  "plan": [
    {
      "id": 1,
      "title": "Review Python fundamentals",
      "description": "Go through data types, loops, functions, and OOP concepts",
      "estimated_minutes": 60,
      "priority": "high"
    }
  ],
  "execution_results": [
    "Plan covers all major interview topics in logical order",
    "Time budget fits within 2 hours/day across 5 days"
  ],
  "critique": "[Score: 8/10 | Quality: good] This plan is thorough and ready to execute.",
  "final_summary": "Goal: Prepare for a Python job interview...\nTasks: 5 | Estimated time: 4.0 hours\nStart with: Review Python fundamentals"
}
```

### Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Check the server is running |
| POST | `/run` | Run the full multi-agent pipeline |
| GET | `/docs` | Interactive API documentation (Swagger UI) |

---

## Error handling

- Empty goal → `400 Bad Request`
- Missing API key → `500` with a clear message
- Any agent failure → returns `"status": "error"` with a description instead of crashing

---

## How the agents work together

The key design decision is that **no agent knows about the others**. Each one just takes an input and returns a dict. The `Orchestrator` is the only place that knows the order and how to pass data between them. This makes each agent easy to test, replace, or extend independently.
