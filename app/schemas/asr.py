from pydantic import BaseModel


class ASRModelResponse(BaseModel):
    id: str
    name: str
    language: str
    language_code: str


class ASRTranscriptionResponse(BaseModel):
    project_id: int
    model: str
    model_name: str
    language: str
    language_code: str
    text: str
    duration_seconds: float
    latency_ms: float
    sample_rate: int
    provider: str
    local: bool
    experiment_id: int | None = None