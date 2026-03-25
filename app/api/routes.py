from fastapi import APIRouter, HTTPException
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