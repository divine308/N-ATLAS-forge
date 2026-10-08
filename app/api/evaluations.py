from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.services.regression import compare_runs

from app.api.deps import get_current_user
from app.core.database import get_db

from app.models.dataset import (
    Dataset,
    DatasetVersion,
)

from app.models.evaluation import (
    EvaluationCase,
    EvaluationRun,
    EvaluationRunTarget,
    EvaluationSuite,
    EvaluationSuiteTarget,
)

from app.models.project import Project
from app.models.project_file import ProjectFile
from app.models.user import User

from app.schemas.evaluation import (
    EvaluationCaseCreate,
    EvaluationCaseResponse,
    EvaluationRunListItem,
    EvaluationRunRequest,
    EvaluationRunResponse,
    EvaluationSuiteCreate,
    EvaluationSuiteResponse,
    EvaluationSuiteUpdate,
    RegressionRequest,
    RegressionResponse,
)

from app.services.evaluator import EvaluationService

from app.services.natlas import (
    NAtlasNotConfiguredError,
    NAtlasRequestError,
    NAtlasService,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["Evaluations"],
)


# ---------------------------------------------------------------------------
# Ownership helpers
# ---------------------------------------------------------------------------

def get_owned_project(
    project_id: int,
    user_id: int,
    db: Session,
) -> Project:
    project = db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user_id,
        )
    )

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    return project


def get_owned_suite(
    suite_id: int,
    user_id: int,
    db: Session,
) -> EvaluationSuite:
    suite = db.scalar(
        select(EvaluationSuite)
        .join(
            Project,
            Project.id == EvaluationSuite.project_id,
        )
        .where(
            EvaluationSuite.id == suite_id,
            Project.owner_id == user_id,
        )
    )

    if not suite:
        raise HTTPException(
            status_code=404,
            detail="Evaluation suite not found.",
        )

    return suite


def get_owned_run(
    run_id: int,
    user_id: int,
    db: Session,
) -> EvaluationRun:
    run = db.scalar(
        select(EvaluationRun)
        .join(
            Project,
            Project.id == EvaluationRun.project_id,
        )
        .where(
            EvaluationRun.id == run_id,
            Project.owner_id == user_id,
        )
    )

    if not run:
        raise HTTPException(
            status_code=404,
            detail="Evaluation run not found.",
        )

    return run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def content_hash(content: str) -> str:
    return hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()


def serialize_target(
    target: EvaluationSuiteTarget,
):
    file = target.project_file

    return {
        "id": target.id,
        "project_file_id": file.id,
        "path": file.path,
        "language": file.language,
        "size": file.size,
        "is_binary": file.is_binary,
    }


def serialize_last_run(
    run: EvaluationRun | None,
):
    if not run:
        return None

    return {
        "id": run.id,
        "status": run.status,
        "score": run.score,
        "total_tests": run.total_tests,
        "passed_tests": run.passed_tests,
        "failed_tests": run.failed_tests,
        "created_at": run.created_at,
    }


def serialize_suite(
    suite: EvaluationSuite,
    last_run: EvaluationRun | None = None,
):
    return {
        "id": suite.id,
        "project_id": suite.project_id,
        "name": suite.name,
        "description": suite.description,
        "category": suite.category,
        "dataset_id": suite.dataset_id,
        "dataset_version": suite.dataset_version,
        "configuration": suite.configuration or {},
        "active": suite.active,
        "case_count": len(suite.cases),
        "target_files": [
            serialize_target(target)
            for target in suite.target_files
        ],
        "last_run": serialize_last_run(last_run),
        "created_at": suite.created_at,
        "updated_at": suite.updated_at,
    }


def validate_dataset_reference(
    project_id: int,
    dataset_id: int | None,
    dataset_version: int | None,
    db: Session,
):
    if dataset_id is None:
        if dataset_version is not None:
            raise HTTPException(
                status_code=400,
                detail="dataset_version requires dataset_id.",
            )

        return None, None

    dataset = db.scalar(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.project_id == project_id,
        )
    )

    if not dataset:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found in this project.",
        )

    version_number = (
        dataset_version
        if dataset_version is not None
        else dataset.latest_version
    )

    version = db.scalar(
        select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset.id,
            DatasetVersion.version == version_number,
        )
    )

    if not version:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Dataset version "
                f"{version_number} not found."
            ),
        )

    return dataset, version


def validate_target_files(
    project_id: int,
    file_ids: list[int],
    db: Session,
):
    if not file_ids:
        return []

    unique_ids = list(
        dict.fromkeys(file_ids)
    )

    files = list(
        db.scalars(
            select(ProjectFile).where(
                ProjectFile.project_id == project_id,
                ProjectFile.id.in_(unique_ids),
            )
        )
    )

    found_ids = {
        file.id
        for file in files
    }

    missing = [
        file_id
        for file_id in unique_ids
        if file_id not in found_ids
    ]

    if missing:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "One or more target files "
                    "do not belong to this project."
                ),
                "file_ids": missing,
            },
        )

    binary_files = [
        file.path
        for file in files
        if file.is_binary
    ]

    if binary_files:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "Binary files cannot be "
                    "evaluation targets."
                ),
                "files": binary_files,
            },
        )

    return files


# ---------------------------------------------------------------------------
# Suite CRUD
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{project_id}/evaluations/suites",
    response_model=list[EvaluationSuiteResponse],
)
def list_suites(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    suites = list(
        db.scalars(
            select(EvaluationSuite)
            .where(
                EvaluationSuite.project_id == project_id,
            )
            .order_by(
                EvaluationSuite.updated_at.desc()
            )
        )
    )

    response = []

    for suite in suites:
        last_run = db.scalar(
            select(EvaluationRun)
            .where(
                EvaluationRun.project_id == project_id,
                EvaluationRun.suite_name == suite.name,
            )
            .order_by(
                EvaluationRun.created_at.desc()
            )
        )

        response.append(
            serialize_suite(
                suite,
                last_run,
            )
        )

    return response


@router.post(
    "/projects/{project_id}/evaluations/suites",
    response_model=EvaluationSuiteResponse,
)
def create_suite(
    project_id: int,
    payload: EvaluationSuiteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    existing = db.scalar(
        select(EvaluationSuite).where(
            EvaluationSuite.project_id == project_id,
            EvaluationSuite.name == payload.name.strip(),
        )
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail=(
                "An evaluation suite with "
                "this name already exists."
            ),
        )

    dataset, version = validate_dataset_reference(
        project_id,
        payload.dataset_id,
        payload.dataset_version,
        db,
    )

    files = validate_target_files(
        project_id,
        payload.target_file_ids,
        db,
    )

    suite = EvaluationSuite(
        project_id=project_id,
        name=payload.name.strip(),
        description=payload.description,
        category=payload.category,
        dataset_id=(
            dataset.id
            if dataset
            else None
        ),
        dataset_version=(
            version.version
            if version
            else None
        ),
        configuration=(
            payload.configuration
            or {}
        ),
    )

    db.add(suite)
    db.flush()

    for file in files:
        db.add(
            EvaluationSuiteTarget(
                suite_id=suite.id,
                project_file_id=file.id,
            )
        )

    db.commit()
    db.refresh(suite)

    return serialize_suite(suite)


@router.get(
    "/evaluations/suites/{suite_id}",
    response_model=EvaluationSuiteResponse,
)
def get_suite(
    suite_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    suite = get_owned_suite(
        suite_id,
        current_user.id,
        db,
    )

    last_run = db.scalar(
        select(EvaluationRun)
        .where(
            EvaluationRun.project_id == suite.project_id,
            EvaluationRun.suite_name == suite.name,
        )
        .order_by(
            EvaluationRun.created_at.desc()
        )
    )

    return serialize_suite(
        suite,
        last_run,
    )


@router.patch(
    "/evaluations/suites/{suite_id}",
    response_model=EvaluationSuiteResponse,
)
def update_suite(
    suite_id: int,
    payload: EvaluationSuiteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    suite = get_owned_suite(
        suite_id,
        current_user.id,
        db,
    )

    if payload.name is not None:
        new_name = payload.name.strip()

        duplicate = db.scalar(
            select(EvaluationSuite).where(
                EvaluationSuite.project_id
                == suite.project_id,
                EvaluationSuite.name
                == new_name,
                EvaluationSuite.id
                != suite.id,
            )
        )

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Another evaluation suite "
                    "already uses this name."
                ),
            )

        suite.name = new_name

    if payload.description is not None:
        suite.description = payload.description

    if payload.category is not None:
        suite.category = payload.category

    if payload.configuration is not None:
        suite.configuration = (
            payload.configuration
        )

    if payload.active is not None:
        suite.active = payload.active

    if (
        payload.dataset_id is not None
        or payload.dataset_version is not None
    ):
        dataset_id = (
            payload.dataset_id
            if payload.dataset_id is not None
            else suite.dataset_id
        )

        version_number = (
            payload.dataset_version
            if payload.dataset_version is not None
            else suite.dataset_version
        )

        dataset, version = (
            validate_dataset_reference(
                suite.project_id,
                dataset_id,
                version_number,
                db,
            )
        )

        suite.dataset_id = (
            dataset.id
            if dataset
            else None
        )

        suite.dataset_version = (
            version.version
            if version
            else None
        )

    if payload.target_file_ids is not None:
        files = validate_target_files(
            suite.project_id,
            payload.target_file_ids,
            db,
        )

        db.query(
            EvaluationSuiteTarget
        ).filter(
            EvaluationSuiteTarget.suite_id
            == suite.id
        ).delete(
            synchronize_session=False
        )

        for file in files:
            db.add(
                EvaluationSuiteTarget(
                    suite_id=suite.id,
                    project_file_id=file.id,
                )
            )

    suite.updated_at = datetime.now(
        timezone.utc
    )

    db.commit()
    db.refresh(suite)

    return serialize_suite(suite)


@router.delete(
    "/evaluations/suites/{suite_id}",
)
def delete_suite(
    suite_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    suite = get_owned_suite(
        suite_id,
        current_user.id,
        db,
    )

    db.delete(suite)
    db.commit()

    return {
        "success": True,
        "message": "Evaluation suite deleted.",
    }


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

@router.get(
    "/evaluations/suites/{suite_id}/cases",
    response_model=list[EvaluationCaseResponse],
)
def list_cases(
    suite_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    suite = get_owned_suite(
        suite_id,
        current_user.id,
        db,
    )

    return list(
        db.scalars(
            select(EvaluationCase)
            .where(
                EvaluationCase.suite_id
                == suite.id,
            )
            .order_by(
                EvaluationCase.position.asc(),
                EvaluationCase.id.asc(),
            )
        )
    )


@router.post(
    "/evaluations/suites/{suite_id}/cases",
    response_model=EvaluationCaseResponse,
)
def create_case(
    suite_id: int,
    payload: EvaluationCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    suite = get_owned_suite(
        suite_id,
        current_user.id,
        db,
    )

    case = EvaluationCase(
        suite_id=suite.id,
        name=payload.name.strip(),
        input=payload.input,
        expected=payload.expected,
        category=payload.category,
        language=payload.language,
        position=payload.position,
        enabled=payload.enabled,
        dataset_record_index=(
            payload.dataset_record_index
        ),
    )

    db.add(case)

    suite.updated_at = datetime.now(
        timezone.utc
    )

    db.commit()
    db.refresh(case)

    return case


@router.patch(
    "/evaluations/cases/{case_id}",
    response_model=EvaluationCaseResponse,
)
def update_case(
    case_id: int,
    payload: EvaluationCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = db.scalar(
        select(EvaluationCase)
        .join(EvaluationSuite)
        .join(Project)
        .where(
            EvaluationCase.id == case_id,
            Project.owner_id
            == current_user.id,
        )
    )

    if not case:
        raise HTTPException(
            status_code=404,
            detail="Evaluation case not found.",
        )

    case.name = payload.name.strip()
    case.input = payload.input
    case.expected = payload.expected
    case.category = payload.category
    case.language = payload.language
    case.position = payload.position
    case.enabled = payload.enabled
    case.dataset_record_index = (
        payload.dataset_record_index
    )

    case.suite.updated_at = datetime.now(
        timezone.utc
    )

    db.commit()
    db.refresh(case)

    return case


@router.delete(
    "/evaluations/cases/{case_id}",
)
def delete_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = db.scalar(
        select(EvaluationCase)
        .join(EvaluationSuite)
        .join(Project)
        .where(
            EvaluationCase.id == case_id,
            Project.owner_id
            == current_user.id,
        )
    )

    if not case:
        raise HTTPException(
            status_code=404,
            detail="Evaluation case not found.",
        )

    case.suite.updated_at = datetime.now(
        timezone.utc
    )

    db.delete(case)
    db.commit()

    return {
        "success": True,
        "message": "Evaluation case deleted.",
    }


# ---------------------------------------------------------------------------
# Run suite
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/evaluations/suites/{suite_id}/run",
    response_model=EvaluationRunResponse,
)
async def run_suite(
    project_id: int,
    suite_id: int,
    payload: EvaluationRunRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    suite = get_owned_suite(
        suite_id,
        current_user.id,
        db,
    )

    if suite.project_id != project_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Evaluation suite does not "
                "belong to this project."
            ),
        )

    if not suite.active:
        raise HTTPException(
            status_code=400,
            detail="This evaluation suite is inactive.",
        )

    cases = list(
        db.scalars(
            select(EvaluationCase)
            .where(
                EvaluationCase.suite_id
                == suite.id,
                EvaluationCase.enabled.is_(True),
            )
            .order_by(
                EvaluationCase.position.asc(),
                EvaluationCase.id.asc(),
            )
        )
    )

    if not cases:
        raise HTTPException(
            status_code=400,
            detail=(
                "This evaluation suite has "
                "no enabled test cases."
            ),
        )

    dataset_version = None

    if suite.dataset_id:
        dataset = db.scalar(
            select(Dataset).where(
                Dataset.id == suite.dataset_id,
                Dataset.project_id == project_id,
            )
        )

        if not dataset:
            raise HTTPException(
                status_code=404,
                detail=(
                    "The suite's dataset "
                    "no longer exists."
                ),
            )

        version_number = (
            suite.dataset_version
            or dataset.latest_version
        )

        dataset_version = db.scalar(
            select(DatasetVersion).where(
                DatasetVersion.dataset_id
                == dataset.id,
                DatasetVersion.version
                == version_number,
            )
        )

        if not dataset_version:
            raise HTTPException(
                status_code=404,
                detail=(
                    "The suite's pinned dataset "
                    "version no longer exists."
                ),
            )

    target_links = list(
        db.scalars(
            select(EvaluationSuiteTarget)
            .where(
                EvaluationSuiteTarget.suite_id
                == suite.id
            )
        )
    )

    # ------------------------------------------------------------------
    # Code snapshot
    # ------------------------------------------------------------------

    snapshots = []

    for link in target_links:
        file = db.get(
            ProjectFile,
            link.project_file_id,
        )

        if not file:
            continue

        snapshots.append(
            EvaluationRunTarget(
                project_file_id=file.id,
                path_snapshot=file.path,
                content_hash=content_hash(
                    file.content or ""
                ),
                language_snapshot=file.language,
                file_size_snapshot=(
                    file.size
                    or len(
                        (
                            file.content
                            or ""
                        ).encode("utf-8")
                    )
                ),
            )
        )

    # ------------------------------------------------------------------
    # Evaluation configuration
    # ------------------------------------------------------------------

    configuration = (
        suite.configuration or {}
    )

    temperature = (
        payload.temperature
        if payload
        else configuration.get(
            "temperature",
            0.2,
        )
    )

    model_name = (
        payload.model_name
        if payload
        and payload.model_name
        else configuration.get(
            "model_name",
            None,
        )
    )

    # ------------------------------------------------------------------
    # N-ATLAS service
    # ------------------------------------------------------------------

    natlas = NAtlasService()

    if not natlas.configured:
        raise HTTPException(
            status_code=503,
            detail="N-ATLAS is not configured.",
        )

    evaluation_service = EvaluationService(
        natlas
    )

    # ------------------------------------------------------------------
    # Evaluate cases
    # ------------------------------------------------------------------

    results = []

    try:
        for case in cases:
            result = (
                await evaluation_service.evaluate_case(
                    input_text=case.input,
                    expected=case.expected,
                    category=case.category,
                    language=case.language,
                    temperature=temperature,
                )
            )

            result["case_id"] = case.id
            result["case_name"] = case.name

            results.append(result)

    except NAtlasNotConfiguredError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    except NAtlasRequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    # ------------------------------------------------------------------
    # Summarize results
    # ------------------------------------------------------------------

    summary = (
        evaluation_service.summarize(
            results
        )
    )

    # EvaluationService returns:
    #
    # {
    #     "total": ...,
    #     "passed": ...,
    #     "failed": ...,
    #     "score": ...,
    #     "categories": {...}
    # }
    #
    # Keep those names here instead of using
    # the old total_tests/passed_tests keys.

    total_tests = summary["total"]
    passed_tests = summary["passed"]
    failed_tests = summary["failed"]
    score = summary["score"]

    # ------------------------------------------------------------------
    # Forge metadata
    # ------------------------------------------------------------------

    metadata = {
        "suite_id": suite.id,
        "suite_name": suite.name,
        "suite_category": suite.category,
        "target_file_count": len(snapshots),
        "target_files": [
            {
                "path": snapshot.path_snapshot,
                "content_hash": snapshot.content_hash,
                "language": snapshot.language_snapshot,
                "size": snapshot.file_size_snapshot,
            }
            for snapshot in snapshots
        ],
        "dataset": (
            {
                "dataset_id": suite.dataset_id,
                "version": (
                    dataset_version.version
                    if dataset_version
                    else None
                ),
                "record_count": (
                    dataset_version.record_count
                    if dataset_version
                    else None
                ),
            }
            if dataset_version
            else None
        ),
        "model_name": model_name,
        "temperature": temperature,
    }

    category_summary = dict(
        summary.get(
            "categories",
            {},
        )
    )

    category_summary["_forge"] = metadata

    # ------------------------------------------------------------------
    # Persist run
    # ------------------------------------------------------------------

    run = EvaluationRun(
        project_id=project_id,
        suite_name=suite.name,
        dataset_id=suite.dataset_id,
        dataset_version=(
            dataset_version.version
            if dataset_version
            else None
        ),
        status="completed",
        total_tests=total_tests,
        passed_tests=passed_tests,
        failed_tests=failed_tests,
        score=score,
        results=results,
        category_summary=category_summary,
    )

    db.add(run)
    db.flush()

    for snapshot in snapshots:
        snapshot.run_id = run.id
        db.add(snapshot)

    db.commit()
    db.refresh(run)

    return run


# ---------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{project_id}/evaluations/runs",
    response_model=list[EvaluationRunListItem],
)
def list_runs(
    project_id: int,
    suite_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    query = select(
        EvaluationRun
    ).where(
        EvaluationRun.project_id
        == project_id
    )

    if suite_id is not None:
        suite = get_owned_suite(
            suite_id,
            current_user.id,
            db,
        )

        if suite.project_id != project_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Evaluation suite does not "
                    "belong to this project."
                ),
            )

        query = query.where(
            EvaluationRun.suite_name
            == suite.name
        )

    runs = list(
        db.scalars(
            query.order_by(
                EvaluationRun.created_at.desc()
            )
        )
    )

    return runs


@router.get(
    "/evaluations/runs/{run_id}",
    response_model=EvaluationRunResponse,
)
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = get_owned_run(
        run_id,
        current_user.id,
        db,
    )

    return run


@router.get(
    "/evaluations/runs/{run_id}/results",
)
def get_run_results(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = get_owned_run(
        run_id,
        current_user.id,
        db,
    )

    # ---------------------------------------------------------------
    # Resolve suite from the Forge metadata stored with the run.
    # We do not rely only on suite_name because suites can be renamed.
    # ---------------------------------------------------------------

    category_summary = run.category_summary or {}

    forge_metadata = (
        category_summary.get("_forge", {})
        if isinstance(category_summary, dict)
        else {}
    )

    suite_id = forge_metadata.get("suite_id")

    suite = None

    if suite_id is not None:
        suite = db.scalar(
            select(EvaluationSuite).where(
                EvaluationSuite.id == suite_id,
                EvaluationSuite.project_id == run.project_id,
            )
        )

    # Backward-compatible fallback for older runs that do not have
    # suite_id in their _forge metadata.
    if suite is None:
        suite = db.scalar(
            select(EvaluationSuite).where(
                EvaluationSuite.project_id == run.project_id,
                EvaluationSuite.name == run.suite_name,
            )
        )

    # ---------------------------------------------------------------
    # Dataset information
    # ---------------------------------------------------------------

    dataset = None

    if run.dataset_id is not None:
        dataset = db.scalar(
            select(Dataset).where(
                Dataset.id == run.dataset_id,
                Dataset.project_id == run.project_id,
            )
        )

    # ---------------------------------------------------------------
    # Codebase snapshot information
    # ---------------------------------------------------------------

    targets = list(
        db.scalars(
            select(EvaluationRunTarget)
            .where(
                EvaluationRunTarget.run_id == run.id
            )
            .order_by(
                EvaluationRunTarget.id.asc()
            )
        )
    )

    target_files = [
        {
            "project_file_id": target.project_file_id,
            "path": target.path_snapshot,
            "content_hash": target.content_hash,
            "language": target.language_snapshot,
            "size": target.file_size_snapshot,
        }
        for target in targets
    ]

    # ---------------------------------------------------------------
    # Results
    # ---------------------------------------------------------------

    raw_results = run.results or []

    results = []

    for result in raw_results:
        item = dict(result)

        # Normalize fields so the frontend has one predictable shape.
        item["case_id"] = item.get("case_id")
        item["case_name"] = item.get(
            "case_name",
            f"Case {item.get('case_id', '—')}",
        )

        item["input"] = item.get(
            "input",
            "",
        )

        item["expected"] = item.get(
            "expected",
            "",
        )

        item["actual"] = item.get(
            "actual",
            "",
        )

        item["passed"] = bool(
            item.get("passed", False)
        )

        item["similarity_score"] = item.get(
            "similarity_score",
            0,
        )

        item["quality_score"] = item.get(
            "quality_score",
            0,
        )

        item["latency_ms"] = item.get(
            "latency_ms"
        )

        item["failure_reasons"] = item.get(
            "failure_reasons",
            [],
        )

        results.append(item)

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------

    return {
        "run": {
            "id": run.id,
            "project_id": run.project_id,
            "suite_id": (
                suite.id
                if suite
                else suite_id
            ),
            "suite_name": run.suite_name,
            "status": run.status,
            "score": run.score,
            "total_tests": run.total_tests,
            "passed_tests": run.passed_tests,
            "failed_tests": run.failed_tests,
            "dataset_id": run.dataset_id,
            "dataset_version": run.dataset_version,
            "created_at": run.created_at,
        },

        "suite": (
            {
                "id": suite.id,
                "name": suite.name,
                "description": suite.description,
                "category": suite.category,
                "active": suite.active,
                "case_count": len(suite.cases),
            }
            if suite
            else None
        ),

        "dataset": (
            {
                "id": dataset.id,
                "name": dataset.name,
                "format": dataset.format,
                "latest_version": dataset.latest_version,
                "version": run.dataset_version,
            }
            if dataset
            else None
        ),

        "results": results,

        "category_summary": category_summary,

        "target_files": target_files,

        "codebase": {
            "target_count": len(target_files),
            "targets": target_files,
        },
    }

# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/evaluations/regression",
    response_model=RegressionResponse,
)
def regression(
    project_id: int,
    payload: RegressionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    if (
        payload.baseline_run_id
        == payload.candidate_run_id
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Baseline and candidate runs "
                "must be different."
            ),
        )

    baseline = get_owned_run(
        payload.baseline_run_id,
        current_user.id,
        db,
    )

    candidate = get_owned_run(
        payload.candidate_run_id,
        current_user.id,
        db,
    )

    if baseline.project_id != project_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Baseline run does not "
                "belong to this project."
            ),
        )

    if candidate.project_id != project_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Candidate run does not "
                "belong to this project."
            ),
        )

    baseline_payload = {
        "id": baseline.id,
        "score": baseline.score,
        "dataset_id": baseline.dataset_id,
        "dataset_version": baseline.dataset_version,
        "results": baseline.results or [],
        "category_summary": (
            baseline.category_summary or {}
        ),
    }

    candidate_payload = {
        "id": candidate.id,
        "score": candidate.score,
        "dataset_id": candidate.dataset_id,
        "dataset_version": candidate.dataset_version,
        "results": candidate.results or [],
        "category_summary": (
            candidate.category_summary or {}
        ),
    }

    comparison = compare_runs(
        baseline_payload,
        candidate_payload,
    )

    return {
        "baseline_run_id": baseline.id,
        "candidate_run_id": candidate.id,
        **comparison,
    }