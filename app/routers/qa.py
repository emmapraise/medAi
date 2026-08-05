from fastapi import APIRouter, HTTPException
from app.config import settings
from app.schemas import AskRequest, AskResponse
from app.services.agent_service import agent_service

router = APIRouter()

@router.post("/ask", response_model=AskResponse, summary="Ask AI Medical Agent (LangGraph CRAG + Follow-up Memory)")
def ask_medical_agent(payload: AskRequest):
    try:
        session = payload.session_id or "default_session"
        model_name = payload.model or settings.DEFAULT_MODEL
        
        result = agent_service.run_qa(
            question=payload.question,
            session_id=session,
            model=model_name,
            max_turns=payload.max_turns or 5
        )
        
        return AskResponse(
            question=payload.question,
            generated_query=result["generated_query"],
            answer=result["answer"],
            session_id=result["session_id"],
            is_relevant=result["is_relevant"],
            is_grounded=result["is_grounded"],
            is_useful=result["is_useful"],
            execution_trace=result["execution_trace"],
            model_used=model_name,
            latency_seconds=result["latency_seconds"],
            prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"],
            total_tokens=result["total_tokens"],
            estimated_cost_usd=result["estimated_cost_usd"],
            turns_executed=result["turns_executed"]
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
