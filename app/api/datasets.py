import json
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.dataset import (
    Dataset,
    DatasetVersion,
)
from app.models.project import Project
from app.models.user import User
from app.schemas.dataset import (
    DatasetRecordResponse,
    DatasetResponse,
    DatasetValidationResponse,
    DatasetVersionResponse,
)
from app.services.dataset_service import (
    DatasetValidationError,
    estimate_size_bytes,
    get_dataset_extension,
    infer_schema,
    parse_dataset,
    serialize_records,
    validate_records,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["Datasets"],
)


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


def get_owned_dataset(
    dataset_id: int,
    user_id: int,
    db: Session,
) -> Dataset:

    dataset = db.scalar(
        select(Dataset)
        .join(Project)
        .where(
            Dataset.id == dataset_id,
            Project.owner_id == user_id,
        )
    )

    if not dataset:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found.",
        )

    return dataset


def get_latest_version(
    dataset: Dataset,
    db: Session,
) -> DatasetVersion | None:

    return db.scalar(
        select(DatasetVersion).where(
            DatasetVersion.dataset_id
            == dataset.id,
            DatasetVersion.version
            == dataset.latest_version,
        )
    )


def dataset_response(
    dataset: Dataset,
    db: Session,
) -> dict:

    latest = get_latest_version(
        dataset,
        db,
    )

    records = (
        latest.records
        if latest and isinstance(
            latest.records,
            list,
        )
        else []
    )

    report = (
        latest.validation_report
        if latest
        and isinstance(
            latest.validation_report,
            dict,
        )
        else {}
    )

    schema = report.get(
        "schema"
    )

    if not isinstance(schema, dict):
        schema = infer_schema(
            records
        )

    size_bytes = estimate_size_bytes(
        records,
        dataset.format,
    )

    return {
        "id": dataset.id,
        "project_id": dataset.project_id,
        "name": dataset.name,
        "description": dataset.description,
        "format": dataset.format,
        "latest_version": dataset.latest_version,
        "created_at": dataset.created_at,
        "updated_at": dataset.updated_at,
        "record_count": (
            latest.record_count
            if latest
            else 0
        ),
        "size_bytes": size_bytes,
        "field_count": len(schema),
        "schema": schema,
        "validation_report": report,
    }


async def parse_uploaded_dataset(
    file: UploadFile,
) -> tuple[
    str,
    list[dict],
    bytes,
]:

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Dataset filename is required.",
        )

    content = await file.read()

    max_bytes = (
        settings.max_dataset_size_mb
        * 1024
        * 1024
    )

    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Dataset exceeds the "
                f"{settings.max_dataset_size_mb}MB limit."
            ),
        )

    try:
        format_name, records = parse_dataset(
            content,
            file.filename,
        )

    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Dataset must use UTF-8 encoding.",
        )

    except DatasetValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    if not records:
        raise HTTPException(
            status_code=400,
            detail="Dataset contains no records.",
        )

    if (
        len(records)
        > settings.max_dataset_records
    ):
        raise HTTPException(
            status_code=413,
            detail=(
                "Dataset exceeds the maximum "
                f"of {settings.max_dataset_records} "
                "records."
            ),
        )

    return (
        format_name,
        records,
        content,
    )


@router.post(
    "/projects/{project_id}/datasets",
    response_model=DatasetResponse,
)
async def upload_dataset(
    project_id: int,
    file: UploadFile = File(...),
    name: str | None = Form(None),
    description: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):

    get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    format_name, records, _ = (
        await parse_uploaded_dataset(file)
    )

    dataset_name = (
        name.strip()
        if name and name.strip()
        else file.filename
    )

    if not dataset_name:
        dataset_name = (
            f"dataset.{format_name}"
        )

    if len(dataset_name) > 150:
        raise HTTPException(
            status_code=400,
            detail="Dataset name must be 150 characters or fewer.",
        )

    if description:
        description = description.strip()

    report = validate_records(
        records
    )

    dataset = Dataset(
        project_id=project_id,
        name=dataset_name,
        description=description,
        format=format_name,
        latest_version=1,
    )

    db.add(dataset)
    db.flush()

    version = DatasetVersion(
        dataset_id=dataset.id,
        version=1,
        record_count=len(records),
        validation_report=report,
        records=records,
    )

    db.add(version)

    db.commit()
    db.refresh(dataset)

    return dataset_response(
        dataset,
        db,
    )


@router.get(
    "/projects/{project_id}/datasets",
    response_model=list[DatasetResponse],
)
def list_project_datasets(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):

    get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    statement = (
        select(Dataset)
        .where(
            Dataset.project_id
            == project_id
        )
        .order_by(
            Dataset.updated_at.desc()
        )
    )

    datasets = list(
        db.scalars(statement).all()
    )

    return [
        dataset_response(
            dataset,
            db,
        )
        for dataset in datasets
    ]


@router.get(
    "/projects/{project_id}/datasets/{dataset_id}",
    response_model=DatasetResponse,
)
def get_project_dataset(
    project_id: int,
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):

    get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    dataset = db.scalar(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.project_id == project_id,
        )
    )

    if not dataset:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found.",
        )

    return dataset_response(
        dataset,
        db,
    )


@router.get(
    "/datasets/{dataset_id}",
    response_model=DatasetResponse,
)
def get_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):

    dataset = get_owned_dataset(
        dataset_id,
        current_user.id,
        db,
    )

    return dataset_response(
        dataset,
        db,
    )


@router.get(
    "/projects/{project_id}/datasets/{dataset_id}/records",
    response_model=DatasetRecordResponse,
)
def get_dataset_records(
    project_id: int,
    dataset_id: int,
    search: str | None = None,
    offset: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):

    get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    dataset = db.scalar(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.project_id == project_id,
        )
    )

    if not dataset:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found.",
        )

    if offset < 0:
        raise HTTPException(
            status_code=400,
            detail="Offset cannot be negative.",
        )

    limit = max(
        1,
        min(limit, 200),
    )

    latest = get_latest_version(
        dataset,
        db,
    )

    records = (
        latest.records
        if latest and isinstance(
            latest.records,
            list,
        )
        else []
    )

    if search and search.strip():

        query = search.strip().lower()

        records = [
            record
            for record in records
            if query
            in json.dumps(
                record,
                ensure_ascii=False,
                default=str,
            ).lower()
        ]

    total = len(records)

    return DatasetRecordResponse(
        records=records[
            offset : offset + limit
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/projects/{project_id}/datasets/{dataset_id}/versions",
    response_model=list[DatasetVersionResponse],
)
def list_dataset_versions(
    project_id: int,
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):

    get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    dataset = db.scalar(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.project_id == project_id,
        )
    )

    if not dataset:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found.",
        )

    statement = (
        select(DatasetVersion)
        .where(
            DatasetVersion.dataset_id
            == dataset.id
        )
        .order_by(
            DatasetVersion.version.desc()
        )
    )

    return list(
        db.scalars(statement).all()
    )


@router.post(
    "/projects/{project_id}/datasets/{dataset_id}/versions",
    response_model=DatasetResponse,
)
async def create_dataset_version(
    project_id: int,
    dataset_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):

    get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    dataset = db.scalar(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.project_id == project_id,
        )
    )

    if not dataset:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found.",
        )

    format_name, records, _ = (
        await parse_uploaded_dataset(file)
    )

    if format_name != dataset.format:
        raise HTTPException(
            status_code=400,
            detail=(
                "New dataset versions must use "
                f"the existing {dataset.format.upper()} format."
            ),
        )

    report = validate_records(
        records
    )

    next_version = (
        dataset.latest_version + 1
    )

    version = DatasetVersion(
        dataset_id=dataset.id,
        version=next_version,
        record_count=len(records),
        validation_report=report,
        records=records,
    )

    dataset.latest_version = (
        next_version
    )

    db.add(version)
    db.commit()
    db.refresh(dataset)

    return dataset_response(
        dataset,
        db,
    )


@router.get(
    "/projects/{project_id}/datasets/{dataset_id}/download",
)
def download_dataset(
    project_id: int,
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):

    get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    dataset = db.scalar(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.project_id == project_id,
        )
    )

    if not dataset:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found.",
        )

    latest = get_latest_version(
        dataset,
        db,
    )

    if not latest:
        raise HTTPException(
            status_code=404,
            detail="Dataset version not found.",
        )

    records = latest.records or []

    content = serialize_records(
        records,
        dataset.format,
    )

    extension = get_dataset_extension(
        dataset.format
    )

    filename = dataset.name

    if not filename.lower().endswith(
        extension
    ):
        filename += extension

    safe_filename = filename.replace(
        '"',
        "",
    )

    return Response(
        content=content,
        media_type=(
            "text/csv"
            if dataset.format == "csv"
            else "application/json"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="{quote(safe_filename)}"'
            )
        },
    )


@router.delete(
    "/projects/{project_id}/datasets/{dataset_id}",
    status_code=204,
)
def delete_dataset(
    project_id: int,
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):

    get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    dataset = db.scalar(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.project_id == project_id,
        )
    )

    if not dataset:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found.",
        )

    db.delete(dataset)
    db.commit()

    return None