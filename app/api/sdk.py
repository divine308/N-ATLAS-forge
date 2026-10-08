from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.sdk import SDKResponse
from app.services.sdk import SDKGenerationError, SDKService


router = APIRouter(
    prefix="/api/v1/projects/{project_id}/sdk",
    tags=["SDK"],
)


@router.get(
    "",
    response_model=SDKResponse,
)
def generate_sdk(
    project_id: int,
    target: str = Query(
        default="fullstack",
        description="Generation target: frontend, backend, fullstack, or sdk.",
    ),
    language: str = Query(
        default="typescript",
        description="Programming language for the generated project.",
    ),
    framework: str = Query(
        default="react-express",
        description="Framework or framework combination for the generated project.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == current_user.id,
        )
    )

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    service = SDKService(db)

    try:
        result = service.generate(
            project=project,
            target=target,
            language=language,
            framework=framework,
        )

    except SDKGenerationError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return SDKResponse(
        target=result.target,
        language=result.language,
        framework=result.framework,
        files=[
            {
                "path": generated_file.path,
                "content": generated_file.content,
            }
            for generated_file in result.files
        ],
        install_command=result.install_command,
        run_command=result.run_command,
        env_filename=result.env_filename,
        env_example=result.env_example,
        usage=result.usage,
        warnings=result.warnings,
        project=result.project,
        workflow=result.workflow,
        manifest=result.manifest,
    )