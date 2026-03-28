from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.orchestrator.coordinator import Orchestrator
from app.orchestrator.conversational_orchestrator import ConversationalOrchestrator
from app.core.session_store import session_store

router = APIRouter()


class AgentRequest(BaseModel):
    goal: str
    context: str = ""  # optional extra info from the user


class AgentResponse(BaseModel):
    status: str
    plan: list
    execution_results: list
    critique: str
    final_summary: str


# ── Chat models ───────────────────────────────────────────────────────────────

class NewSessionResponse(BaseModel):
    session_id: str
    message: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    session_id: str
    assistant_message: str
    structured_data: Optional[dict] = None
    action: str


# ── Chat endpoints ─────────────────────────────────────────────────────────────

@router.post("/chat/new", response_model=NewSessionResponse)
def new_chat_session():
    """
    Creates a new conversation session.
    Call this first — it returns a session_id you use for all /chat requests.
    """
    sid = session_store.create_session()
    return NewSessionResponse(
        session_id=sid,
        message="Session created. Send your goal to POST /chat."
    )


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Send a message in an existing session.
    The assistant will respond conversationally and only run the full
    planning pipeline after you describe a goal and confirm.
    """
    if not session_store.session_exists(request.session_id):
        raise HTTPException(
            status_code=404,
            detail="Session not found. Create one first with POST /chat/new."
        )
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        orchestrator = ConversationalOrchestrator()
        result = orchestrator.run(
            session_id=request.session_id,
            user_message=request.message
        )
        return ChatResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        )


# ── Original endpoint (unchanged) ─────────────────────────────────────────────

@router.post("/run", response_model=AgentResponse)
def run_agent(request: AgentRequest):
    if not request.goal or not request.goal.strip():
        raise HTTPException(status_code=400, detail="Goal cannot be empty.")

    try:
        orchestrator = Orchestrator()
        result = orchestrator.run(goal=request.goal, context=request.context)
        return AgentResponse(**result)
    except ValueError as e:
        # Raised by LLMClient when ANTHROPIC_API_KEY is missing
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        )