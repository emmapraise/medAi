import os
from fastapi import APIRouter, HTTPException
from app.schemas import IngestResponse
from app.services.search_service import search_engine

router = APIRouter()

@router.post("/ingest", response_model=IngestResponse, summary="Trigger Dataset Ingestion")
def trigger_ingestion(dataset_path: str = "dataset/medquad.csv"):
    if not os.path.exists(dataset_path):
        raise HTTPException(status_code=404, detail=f"Dataset file '{dataset_path}' not found on server.")
    
    count = search_engine.ingest_dataset(csv_path=dataset_path)
    return IngestResponse(
        status="success",
        records_ingested=count,
        collection_name=search_engine.client and "medical_knowledge_base_hybrid" or ""
    )
