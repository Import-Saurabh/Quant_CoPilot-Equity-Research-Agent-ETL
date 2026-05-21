from fastapi import APIRouter, HTTPException
from app.models.schemas import StockRequest, PipelineResponse
from app.services.pipeline_service import execute_pipeline

router = APIRouter()


@router.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


@router.post("/ingest", response_model=PipelineResponse)
def analyze_stock(payload: StockRequest):
    try:
        result = execute_pipeline(payload.symbol)
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )