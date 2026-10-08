import io
import json
import re
import zipfile
from pathlib import PurePosixPath
from urllib.parse import urlparse

import requests

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.project import Project
from app.models.project_file import ProjectFile
from app.models.user import User
from app.schemas.project import (
    ProjectCreate,
    ProjectFileDetailResponse,
    ProjectFileResponse,
    ProjectFileUpdate,
    ProjectImportResponse,
    ProjectResponse,
    ProjectUpdate,
)


router = APIRouter(
    prefix="/api/v1/projects",
    tags=["Projects"],
)


MAX_FILE_SIZE = 2 * 1024 * 1024
MAX_TOTAL_IMPORT_SIZE = 100 * 1024 * 1024

IGNORED_DIRECTORIES = {
    "node_modules",
    ".git",
    ".next",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
    ".idea",
    ".vscode",
}

LANGUAGE_BY_EXTENSION = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".py": "python",
    ".java": "java",
    ".kt": "kotlin",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".rb": "ruby",
    ".swift": "swift",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".sql": "sql",
    ".sh": "shell",
    ".bash": "shell",
    ".xml": "xml",
    ".env": "dotenv",
}


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


def detect_language(path: str) -> str | None:
    name = path.lower()

    if name.endswith(".env"):
        return "dotenv"

    extension = PurePosixPath(name).suffix

    return LANGUAGE_BY_EXTENSION.get(
        extension
    )


def should_ignore(path: str) -> bool:
    parts = [
        part
        for part in PurePosixPath(path).parts
        if part not in (".", "")
    ]

    return any(
        part in IGNORED_DIRECTORIES
        for part in parts
    )


def safe_project_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip("/")

    pure = PurePosixPath(normalized)

    if pure.is_absolute():
        raise ValueError("Absolute paths are not allowed.")

    if ".." in pure.parts:
        raise ValueError(
            "Parent directory traversal is not allowed."
        )

    if should_ignore(normalized):
        raise ValueError("Ignored project path.")

    return str(pure)


def is_text_file(data: bytes) -> bool:
    if b"\x00" in data:
        return False

    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def detect_natlas_usage(
    files: list[dict],
) -> list[dict]:

    findings = []

    patterns = [
        (
            "N-ATLAS",
            re.compile(
                r"\bN[-_ ]?ATLAS\b",
                re.IGNORECASE,
            ),
        ),
        (
            "natlas",
            re.compile(
                r"\bnatlas\b",
                re.IGNORECASE,
            ),
        ),
        (
            "N-ATLAS API",
            re.compile(
                r"n[-_ ]?atlas.*(?:api|chat|generate|completion)",
                re.IGNORECASE,
            ),
        ),
    ]

    for file in files:
        content = file.get("content", "")

        if not content:
            continue

        lines = content.splitlines()

        for line_number, line in enumerate(
            lines,
            start=1,
        ):
            for label, pattern in patterns:
                if pattern.search(line):
                    findings.append(
                        {
                            "path": file["path"],
                            "line": line_number,
                            "type": label,
                            "match": line.strip()[:500],
                        }
                    )

                    break

    return findings


def replace_project_files(
    db: Session,
    project_id: int,
    files: list[dict],
) -> int:

    db.execute(
        delete(ProjectFile).where(
            ProjectFile.project_id == project_id
        )
    )

    imported = 0

    for file in files:
        if file.get("is_binary"):
            continue

        content = file.get("content", "")

        if len(
            content.encode("utf-8")
        ) > MAX_FILE_SIZE:
            continue

        db.add(
            ProjectFile(
                project_id=project_id,
                path=file["path"],
                content=content,
                language=detect_language(
                    file["path"]
                ),
                size=len(
                    content.encode("utf-8")
                ),
                is_binary=False,
            )
        )

        imported += 1

    return imported


def project_metadata(
    files: list[dict],
) -> tuple[list[str], list[dict]]:

    languages = sorted(
        {
            detect_language(file["path"])
            for file in files
            if detect_language(file["path"])
        }
    )

    natlas = detect_natlas_usage(files)

    return languages, natlas


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = Project(
        owner_id=current_user.id,
        name=payload.name.strip(),
        description=payload.description,
        default_language=payload.default_language,
        model_name="N-ATLAS",
        configuration={},
    )

    db.add(project)
    db.commit()
    db.refresh(project)

    return project


@router.get(
    "",
    response_model=list[ProjectResponse],
)
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    statement = (
        select(Project)
        .where(
            Project.owner_id == current_user.id
        )
        .order_by(
            Project.created_at.desc()
        )
    )

    return list(
        db.scalars(statement).all()
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_owned_project(
        project_id,
        current_user.id,
        db,
    )


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    update_data = payload.model_dump(
        exclude_unset=True
    )

    if (
        "name" in update_data
        and update_data["name"]
    ):
        update_data["name"] = (
            update_data["name"].strip()
        )

    for field, value in update_data.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)

    return project


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    db.delete(project)
    db.commit()

    return None


# ============================================================
# PROJECT FILES
# ============================================================


@router.get(
    "/{project_id}/files",
    response_model=list[ProjectFileResponse],
)
def list_project_files(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    statement = (
        select(ProjectFile)
        .where(
            ProjectFile.project_id
            == project_id
        )
        .order_by(ProjectFile.path.asc())
    )

    return list(
        db.scalars(statement).all()
    )


@router.get(
    "/{project_id}/files/{file_id}",
    response_model=ProjectFileDetailResponse,
)
def get_project_file(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    file = db.scalar(
        select(ProjectFile).where(
            ProjectFile.id == file_id,
            ProjectFile.project_id == project_id,
        )
    )

    if not file:
        raise HTTPException(
            status_code=404,
            detail="Project file not found.",
        )

    return file


@router.patch(
    "/{project_id}/files/{file_id}",
    response_model=ProjectFileDetailResponse,
)
def update_project_file(
    project_id: int,
    file_id: int,
    payload: ProjectFileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    file = db.scalar(
        select(ProjectFile).where(
            ProjectFile.id == file_id,
            ProjectFile.project_id == project_id,
        )
    )

    if not file:
        raise HTTPException(
            status_code=404,
            detail="Project file not found.",
        )

    if len(
        payload.content.encode("utf-8")
    ) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File is too large.",
        )

    file.content = payload.content
    file.size = len(
        payload.content.encode("utf-8")
    )

    db.commit()
    db.refresh(file)

    return file


# ============================================================
# ZIP IMPORT
# ============================================================


@router.post(
    "/{project_id}/import/zip",
    response_model=ProjectImportResponse,
)
async def import_project_zip(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="A project ZIP file is required.",
        )

    if not file.filename.lower().endswith(
        ".zip"
    ):
        raise HTTPException(
            status_code=400,
            detail="Only ZIP project files are supported.",
        )

    data = await file.read()

    if len(data) > MAX_TOTAL_IMPORT_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Project archive is too large.",
        )

    try:
        archive = zipfile.ZipFile(
            io.BytesIO(data)
        )
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is not a valid ZIP archive.",
        )

    files = []
    total_size = 0

    for entry in archive.infolist():
        if entry.is_dir():
            continue

        try:
            path = safe_project_path(
                entry.filename
            )
        except ValueError:
            continue

        if not path:
            continue

        raw = archive.read(entry)

        total_size += len(raw)

        if total_size > MAX_TOTAL_IMPORT_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Extracted project is too large.",
            )

        if len(raw) > MAX_FILE_SIZE:
            continue

        if not is_text_file(raw):
            continue

        files.append(
            {
                "path": path,
                "content": raw.decode("utf-8"),
                "is_binary": False,
            }
        )

    if not files:
        raise HTTPException(
            status_code=400,
            detail="No readable source files were found in the project.",
        )

    languages, natlas = project_metadata(
        files
    )

    imported = replace_project_files(
        db,
        project.id,
        files,
    )

    project.configuration = {
        **(project.configuration or {}),
        "source_type": "zip",
        "source_url": None,
        "source_filename": file.filename,
        "imported_file_count": imported,
        "detected_languages": languages,
        "natlas_usage": natlas,
    }

    db.commit()
    db.refresh(project)

    return ProjectImportResponse(
        project=project,
        files_imported=imported,
        source_type="zip",
        source_url=None,
        detected_languages=languages,
        natlas_usage=natlas,
    )


# ============================================================
# GITHUB IMPORT
# ============================================================


def parse_github_url(
    repository_url: str,
) -> tuple[str, str]:

    parsed = urlparse(
        repository_url.strip()
    )

    if parsed.netloc.lower() not in {
        "github.com",
        "www.github.com",
    }:
        raise HTTPException(
            status_code=400,
            detail="Only GitHub repository URLs are supported.",
        )

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    if len(parts) < 2:
        raise HTTPException(
            status_code=400,
            detail="Invalid GitHub repository URL.",
        )

    owner = parts[0]
    repo = parts[1]

    if repo.endswith(".git"):
        repo = repo[:-4]

    if not owner or not repo:
        raise HTTPException(
            status_code=400,
            detail="Invalid GitHub repository URL.",
        )

    return owner, repo


def github_request(
    url: str,
) -> requests.Response:

    response = requests.get(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
    )

    if response.status_code >= 400:
        detail = "Unable to read GitHub repository."

        try:
            payload = response.json()

            if payload.get("message"):
                detail = payload["message"]
        except Exception:
            pass

        raise HTTPException(
            status_code=400,
            detail=detail,
        )

    return response


def get_github_files(
    owner: str,
    repo: str,
) -> list[dict]:

    repository = github_request(
        f"https://api.github.com/repos/{owner}/{repo}"
    ).json()

    default_branch = repository.get(
        "default_branch"
    )

    if not default_branch:
        raise HTTPException(
            status_code=400,
            detail="GitHub repository has no default branch.",
        )

    tree = github_request(
        "https://api.github.com/repos/"
        f"{owner}/{repo}/git/trees/"
        f"{default_branch}?recursive=1"
    ).json()

    files = []

    for item in tree.get("tree", []):
        if item.get("type") != "blob":
            continue

        path = item.get("path", "")

        try:
            path = safe_project_path(path)
        except ValueError:
            continue

        size = item.get("size", 0)

        if size > MAX_FILE_SIZE:
            continue

        if not detect_language(path):
            continue

        content_response = github_request(
            "https://raw.githubusercontent.com/"
            f"{owner}/{repo}/{default_branch}/"
            f"{path}"
        )

        raw = content_response.content

        if not is_text_file(raw):
            continue

        files.append(
            {
                "path": path,
                "content": raw.decode("utf-8"),
                "is_binary": False,
            }
        )

        if len(
            files
        ) > 5000:
            break

    return files


@router.post(
    "/{project_id}/import/github",
    response_model=ProjectImportResponse,
)
def import_project_github(
    project_id: int,
    repository_url: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = get_owned_project(
        project_id,
        current_user.id,
        db,
    )

    owner, repo = parse_github_url(
        repository_url
    )

    files = get_github_files(
        owner,
        repo,
    )

    if not files:
        raise HTTPException(
            status_code=400,
            detail="No readable source files were found in the GitHub repository.",
        )

    languages, natlas = project_metadata(
        files
    )

    imported = replace_project_files(
        db,
        project.id,
        files,
    )

    normalized_url = (
        f"https://github.com/{owner}/{repo}"
    )

    project.configuration = {
        **(project.configuration or {}),
        "source_type": "github",
        "source_url": normalized_url,
        "source_repository": f"{owner}/{repo}",
        "imported_file_count": imported,
        "detected_languages": languages,
        "natlas_usage": natlas,
    }

    db.commit()
    db.refresh(project)

    return ProjectImportResponse(
        project=project,
        files_imported=imported,
        source_type="github",
        source_url=normalized_url,
        detected_languages=languages,
        natlas_usage=natlas,
    )