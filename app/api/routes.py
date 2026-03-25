from fastapi import APIRouter
from pydantic import BaseModel
from app.orchestrator.coordinator import Orchestrator

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
    orchestrator = Orchestrator()
    result = orchestrator.run(goal=request.goal, context=request.context)
    return AgentResponse(**result)