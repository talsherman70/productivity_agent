from fastapi import APIRouter
from pydantic import BaseModel

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


@router.post("/run", response_model=AgentResponse)
def run_agent(request: AgentRequest):
    # Placeholder — will be wired to the orchestrator in Phase 7
    return AgentResponse(
        status="ok",
        plan=[],
        execution_results=[],
        critique="",
        final_summary=f"Received your goal: '{request.goal}'. Agents not yet connected."
    )