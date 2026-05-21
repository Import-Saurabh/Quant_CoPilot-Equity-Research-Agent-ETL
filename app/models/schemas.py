from pydantic import BaseModel, Field


class StockRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)


class PipelineResponse(BaseModel):
    status: str
    symbol: str
    message: str