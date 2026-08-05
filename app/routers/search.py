from fastapi import APIRouter, HTTPException
from app.schemas import SearchRequest, SearchResponse
from app.services.search_service import search_engine

router = APIRouter()

@router.post("/search", response_model=SearchResponse, summary="Execute Hybrid Vector Search")
def search_knowledge_base(payload: SearchRequest):
    try:
        results = search_engine.hybrid_search(query_text=payload.query, top_k=payload.top_k)
        return SearchResponse(
            query=payload.query,
            results_count=len(results),
            results=results
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
