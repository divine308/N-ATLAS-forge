# from pydantic import BaseModel, Field


# class PlaygroundMessage(BaseModel):
#     role: str = Field(
#         pattern="^(system|user|assistant)$"
#     )

#     content: str = Field(
#         min_length=1,
#         max_length=20000,
#     )


# class PlaygroundRequest(BaseModel):
#     project_id: int

#     messages: list[PlaygroundMessage] = Field(
#         min_length=1,
#         max_length=100,
#     )

#     temperature: float = Field(
#         default=0.7,
#         ge=0,
#         le=2,
#     )

#     max_tokens: int = Field(
#         default=512,
#         ge=1,
#         le=8192,
#     )

#     language: str = "nigerian_english"

#     experiment_name: str = Field(
#         default="Playground Experiment",
#         max_length=150,
#     )


# class PlaygroundResponse(BaseModel):
#     project_id: int
#     experiment_id: int | None
#     model: str
#     content: str
#     latency_ms: float
#     provider_configured: bool
#     raw_response: dict | None = None

from pydantic import BaseModel, Field


class PlaygroundMessage(BaseModel):
    role: str = Field(
        pattern="^(system|user|assistant)$"
    )

    content: str = Field(
        min_length=1,
        max_length=20000,
    )


class PlaygroundRequest(BaseModel):
    project_id: int

    messages: list[PlaygroundMessage] = Field(
        min_length=1,
        max_length=100,
    )

    temperature: float = Field(
        default=0.7,
        ge=0,
        le=2,
    )

    max_tokens: int = Field(
        default=512,
        ge=1,
        le=8192,
    )

    language: str = "nigerian_english"

    experiment_name: str = Field(
        default="Playground Experiment",
        max_length=150,
    )


class PlaygroundResponse(BaseModel):
    project_id: int
    experiment_id: int | None
    model: str
    content: str
    latency_ms: float
    provider_configured: bool
    raw_response: dict | None = None