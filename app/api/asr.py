from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.experiment import Experiment
from app.models.project import Project
from app.models.user import User
from app.schemas.asr import (
    ASRModelResponse,
    ASRTranscriptionResponse,
)
from app.services.natlas import (
    NAtlasService,
)
from app.services.natlas_asr import (
    NATLAS_ASR_MODELS,
    NAtlasASRError,
    NAtlasASRNotConfiguredError,
    NAtlasASRRequestError,
    NAtlasASRService,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["N-ATLAS ASR"],
)


@router.get(
    "/asr/models",
    response_model=list[
        ASRModelResponse
    ],
)
async def list_asr_models(
    current_user: User = Depends(
        get_current_user
    ),
):

    return [
        ASRModelResponse(
            id=model_id,
            name=info["name"],
            language=info["language"],
            language_code=info[
                "language_code"
            ],
        )
        for model_id, info
        in NATLAS_ASR_MODELS.items()
    ]


@router.post(
    "/projects/{project_id}/asr/transcribe",
    response_model=ASRTranscriptionResponse,
)
async def transcribe_audio(
    project_id: int,
    model: str,
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):

    project = db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id
            == current_user.id,
        )
    )

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    try:
        model = (
            NAtlasASRService.validate_model(
                model
            )
        )

    except NAtlasASRRequestError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    if not audio.filename:
        raise HTTPException(
            status_code=400,
            detail="An audio file is required.",
        )

    try:
        audio_bytes = await audio.read()

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unable to read the uploaded "
                f"audio file: {exc}"
            ),
        )

    if not audio_bytes:
        raise HTTPException(
            status_code=400,
            detail="The uploaded audio file is empty.",
        )

    service = NAtlasASRService()

    try:

        result = await service.transcribe(
            model_name=model,
            audio_bytes=audio_bytes,
            filename=audio.filename,
        )

        experiment = Experiment(
            project_id=project.id,
            name=(
                f"ASR / "
                f"{result['model_name']}"
            ),
            system_prompt=(
                "N-ATLAS automatic speech "
                "recognition transcription."
            ),
            user_prompt=(
                f"Audio file: "
                f"{audio.filename}"
            ),
            language=result[
                "language"
            ],
            model_name=model,
            request_payload={
                "type": "speech_recognition",
                "model": model,
                "filename": audio.filename,
                "content_type": audio.content_type,
                "duration_seconds": result[
                    "duration_seconds"
                ],
                "sample_rate": result[
                    "sample_rate"
                ],
            },
            response_payload={
                "text": result["text"],
                "model": model,
                "language": result[
                    "language"
                ],
                "duration_seconds": result[
                    "duration_seconds"
                ],
            },
            latency_ms=result[
                "latency_ms"
            ],
        )

        db.add(experiment)
        db.commit()
        db.refresh(experiment)

        return ASRTranscriptionResponse(
            project_id=project.id,
            model=result["model"],
            model_name=result[
                "model_name"
            ],
            language=result[
                "language"
            ],
            language_code=result[
                "language_code"
            ],
            text=result["text"],
            duration_seconds=result[
                "duration_seconds"
            ],
            latency_ms=result[
                "latency_ms"
            ],
            sample_rate=result[
                "sample_rate"
            ],
            provider=result[
                "provider"
            ],
            local=result[
                "local"
            ],
            experiment_id=experiment.id,
        )

    except NAtlasASRNotConfiguredError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )

    except NAtlasASRRequestError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except NAtlasASRError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=(
                "Unexpected N-ATLAS ASR error: "
                f"{exc}"
            ),
        )