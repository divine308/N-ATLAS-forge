from typing import Any

from pydantic import BaseModel, Field


class SDKFile(BaseModel):
    path: str
    content: str


class SDKResponse(BaseModel):
    target: str
    language: str
    framework: str

    files: list[SDKFile] = Field(
        default_factory=list
    )

    install_command: str = ""

    run_command: str = ""

    env_filename: str = ".env.example"

    env_example: str = ""

    usage: str = ""

    warnings: list[str] = Field(
        default_factory=list
    )

    project: dict[str, Any] = Field(
        default_factory=dict
    )

    workflow: dict[str, Any] = Field(
        default_factory=dict
    )

    manifest: dict[str, Any] = Field(
        default_factory=dict
    )