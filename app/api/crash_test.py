import asyncio
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.project import Project
from app.models.user import User
from app.services.crash_test import CrashTestService
from app.services.evaluator import EvaluationService
from app.services.natlas import NAtlasService


router = APIRouter(
    prefix="/api/v1/projects/{project_id}",
    tags=["Crash Test"],
)


# Development-time registry for active/completed Crash Test runs.
# The actual test results still come directly from N-ATLAS.
crash_test_runs = {}


async def execute_crash_test(
    run_id: str,
):
    try:
        natlas = NAtlasService()

        evaluator = EvaluationService(
            natlas=natlas
        )

        crash_test = CrashTestService(
            evaluator=evaluator
        )

        result = await crash_test.run()

        crash_test_runs[run_id] = {
            "status": "completed",
            "result": result,
            "error": None,
        }

    except Exception as exc:
        crash_test_runs[run_id] = {
            "status": "failed",
            "result": None,
            "error": str(exc),
        }


@router.post("/crash-test")
async def start_crash_test(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
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

    natlas = NAtlasService()

    if not natlas.configured:
        raise HTTPException(
            status_code=503,
            detail="N-ATLAS provider is not configured.",
        )

    run_id = str(uuid4())

    crash_test_runs[run_id] = {
        "status": "running",
        "result": None,
        "error": None,
    }

    asyncio.create_task(
        execute_crash_test(run_id)
    )

    return {
        "run_id": run_id,
        "status": "running",
    }


@router.get("/crash-test/{run_id}")
async def get_crash_test(
    project_id: int,
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
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

    run = crash_test_runs.get(run_id)

    if not run:
        raise HTTPException(
            status_code=404,
            detail="Crash Test run not found.",
        )

    return {
        "run_id": run_id,
        "status": run["status"],
        "result": run["result"],
        "error": run["error"],
    }