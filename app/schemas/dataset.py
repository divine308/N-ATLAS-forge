from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DatasetCreate(BaseModel):
    project_id: int

    name: str = Field(
        min_length=2,
        max_length=150,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )


class DatasetSchemaField(BaseModel):
    type: str
    nullable: bool = False
    present: int = 0
    missing: int = 0
    types: dict[str, int] = {}


class DatasetResponse(BaseModel):
    id: int
    project_id: int
    name: str
    description: str | None
    format: str
    latest_version: int
    created_at: datetime
    updated_at: datetime

    record_count: int = 0
    size_bytes: int = 0
    field_count: int = 0
    schema: dict[str, Any] = {}
    validation_report: dict[str, Any] = {}

    model_config = {
        "from_attributes": True,
    }


class DatasetRecordResponse(BaseModel):
    records: list[dict[str, Any]]
    total: int
    offset: int
    limit: int


class DatasetVersionResponse(BaseModel):
    id: int
    dataset_id: int
    version: int
    record_count: int
    created_at: datetime
    validation_report: dict[str, Any] | None = None

    model_config = {
        "from_attributes": True,
    }


class DatasetValidationResponse(BaseModel):
    dataset_id: int
    version: int
    record_count: int
    report: dict