from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=150,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )

    default_language: str = "nigerian_english"


class ProjectUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=150,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )

    default_language: str | None = None

    model_name: str | None = None

    configuration: dict | None = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str | None
    default_language: str
    model_name: str
    configuration: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
    }


class ProjectFileResponse(BaseModel):
    id: int
    path: str
    language: str | None
    size: int
    is_binary: bool
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
    }


class ProjectFileDetailResponse(ProjectFileResponse):
    content: str


class ProjectFileUpdate(BaseModel):
    content: str


class ProjectImportResponse(BaseModel):
    project: ProjectResponse
    files_imported: int
    source_type: str
    source_url: str | None = None
    detected_languages: list[str] = Field(
        default_factory=list
    )
    natlas_usage: list[dict] = Field(
        default_factory=list
    )