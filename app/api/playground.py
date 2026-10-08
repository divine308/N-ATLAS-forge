# from fastapi import (
#     APIRouter,
#     Depends,
#     HTTPException,
# )
# from sqlalchemy import select
# from sqlalchemy.orm import Session

# from app.api.deps import get_current_user
# from app.core.database import get_db
# from app.models.experiment import Experiment
# from app.models.project import Project
# from app.models.user import User
# from app.schemas.playground import (
#     PlaygroundRequest,
#     PlaygroundResponse,
# )
# from app.services.natlas import (
#     NAtlasNotConfiguredError,
#     NAtlasRequestError,
#     NAtlasService,
# )


# router = APIRouter(
#     prefix="/api/v1/projects/{project_id}/playground",
#     tags=["Playground"],
# )


# LANGUAGE_INSTRUCTIONS = {
#     "english": (
#         "Always respond in English. "
#         "Use clear, natural English."
#     ),
#     "nigerian-english": (
#         "Always respond in Nigerian Pidgin. "
#         "Use natural Nigerian Pidgin as commonly spoken in Nigeria. "
#         "Do not switch to Yoruba, Hausa, Igbo, or another language "
#         "unless the user explicitly requests it."
#     ),
#     "nigerian_english": (
#         "Always respond in Nigerian Pidgin. "
#         "Use natural Nigerian Pidgin as commonly spoken in Nigeria. "
#         "Do not switch to Yoruba, Hausa, Igbo, or another language "
#         "unless the user explicitly requests it."
#     ),
#     "pidgin": (
#         "Always respond in Nigerian Pidgin. "
#         "Use natural Nigerian Pidgin as commonly spoken in Nigeria. "
#         "Do not switch to Yoruba, Hausa, Igbo, or another language "
#         "unless the user explicitly requests it."
#     ),
#     "yoruba": (
#         "Always respond in Yoruba. "
#         "Use natural, grammatically correct Yoruba. "
#         "Do not switch to English, Hausa, Igbo, or another language "
#         "unless the user explicitly requests it."
#     ),
#     "hausa": (
#         "Always respond in Hausa. "
#         "Use natural, grammatically correct Hausa. "
#         "Do not switch to English, Yoruba, Igbo, or another language "
#         "unless the user explicitly requests it."
#     ),
#     "igbo": (
#         "Always respond in Igbo. "
#         "Use natural, grammatically correct Igbo. "
#         "Do not switch to English, Yoruba, Hausa, or another language "
#         "unless the user explicitly requests it."
#     ),
# }


# @router.post(
#     "/chat",
#     response_model=PlaygroundResponse,
# )
# async def playground_chat(
#     project_id: int,
#     payload: PlaygroundRequest,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(
#         get_current_user
#     ),
# ):

#     if project_id != payload.project_id:
#         raise HTTPException(
#             status_code=400,
#             detail="Project ID mismatch.",
#         )

#     project = db.scalar(
#         select(Project).where(
#             Project.id == project_id,
#             Project.owner_id
#             == current_user.id,
#         )
#     )

#     if not project:
#         raise HTTPException(
#             status_code=404,
#             detail="Project not found.",
#         )

#     natlas = NAtlasService()

#     try:

#         language_instruction = LANGUAGE_INSTRUCTIONS.get(
#             payload.language,
#             LANGUAGE_INSTRUCTIONS["english"],
#         )

#         system_message = {
#             "role": "system",
#             "content": (
#                 "You are an AI assistant.\n\n"
#                 f"{language_instruction}\n\n"
#                 "Follow the selected language consistently "
#                 "throughout your response."
#             ),
#         }

#         conversation_messages = [
#             system_message,
#             *[
#                 message.model_dump()
#                 for message in payload.messages
#                 if message.role != "system"
#             ],
#         ]

#         response = await natlas.chat(
#             messages=conversation_messages,
#             temperature=payload.temperature,
#             max_tokens=payload.max_tokens,
#         )

#         content = (
#             natlas.extract_text(
#                 response["data"]
#             )
#         )

#         experiment = Experiment(
#             project_id=project.id,
#             name=payload.experiment_name,
#             system_prompt=system_message[
#                 "content"
#             ],
#             user_prompt=next(
#                 (
#                     message.content
#                     for message in reversed(
#                         payload.messages
#                     )
#                     if message.role
#                     == "user"
#                 ),
#                 "",
#             ),
#             language=payload.language,
#             model_name=project.model_name,
#             request_payload={
#                 "messages": conversation_messages,
#                 "temperature": (
#                     payload.temperature
#                 ),
#                 "max_tokens": (
#                     payload.max_tokens
#                 ),
#             },
#             response_payload=response[
#                 "data"
#             ],
#             latency_ms=response[
#                 "latency_ms"
#             ],
#         )

#         db.add(experiment)
#         db.commit()
#         db.refresh(experiment)

#         return PlaygroundResponse(
#             project_id=project.id,
#             experiment_id=experiment.id,
#             model=project.model_name,
#             content=content,
#             latency_ms=response[
#                 "latency_ms"
#             ],
#             provider_configured=True,
#             raw_response=response[
#                 "data"
#             ],
#         )

#     except NAtlasNotConfiguredError:

#         return PlaygroundResponse(
#             project_id=project.id,
#             experiment_id=None,
#             model=project.model_name,
#             content="",
#             latency_ms=0,
#             provider_configured=False,
#             raw_response={
#                 "message": (
#                     "N-ATLAS provider is not configured."
#                 )
#             },
#         )

#     except NAtlasRequestError as exc:

#         raise HTTPException(
#             status_code=502,
#             detail=str(exc),
#         )

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.experiment import Experiment
from app.models.project import Project
from app.models.user import User
from app.schemas.playground import (
    PlaygroundRequest,
    PlaygroundResponse,
)
from app.services.natlas import (
    NAtlasNotConfiguredError,
    NAtlasRequestError,
    NAtlasService,
)


router = APIRouter(
    prefix="/api/v1/projects/{project_id}/playground",
    tags=["Playground"],
)


LANGUAGE_INSTRUCTIONS = {
    "english": (
        "Always respond in English. "
        "Use clear, natural English."
    ),
    "nigerian-english": (
        "Always respond in Nigerian Pidgin. "
        "Use natural Nigerian Pidgin as commonly spoken in Nigeria. "
        "Do not switch to Yoruba, Hausa, Igbo, or another language "
        "unless the user explicitly requests it."
    ),
    "nigerian_english": (
        "Always respond in Nigerian Pidgin. "
        "Use natural Nigerian Pidgin as commonly spoken in Nigeria. "
        "Do not switch to Yoruba, Hausa, Igbo, or another language "
        "unless the user explicitly requests it."
    ),
    "pidgin": (
        "Always respond in Nigerian Pidgin. "
        "Use natural Nigerian Pidgin as commonly spoken in Nigeria. "
        "Do not switch to Yoruba, Hausa, Igbo, or another language "
        "unless the user explicitly requests it."
    ),
    "yoruba": (
        "Always respond in Yoruba. "
        "Use natural, grammatically correct Yoruba. "
        "Do not switch to English, Hausa, Igbo, or another language "
        "unless the user explicitly requests it."
    ),
    "hausa": (
        "Always respond in Hausa. "
        "Use natural, grammatically correct Hausa. "
        "Do not switch to English, Yoruba, Igbo, or another language "
        "unless the user explicitly requests it."
    ),
    "igbo": (
        "Always respond in Igbo. "
        "Use natural, grammatically correct Igbo. "
        "Do not switch to English, Yoruba, Hausa, or another language "
        "unless the user explicitly requests it."
    ),
}


def get_project_configuration(
    project: Project,
) -> dict:

    configuration = (
        project.configuration
        if isinstance(
            project.configuration,
            dict,
        )
        else {}
    )

    return configuration


def build_system_prompt(
    project: Project,
    language: str,
) -> str:

    configuration = get_project_configuration(
        project
    )

    configured_prompt = str(
        configuration.get(
            "system_prompt",
            "",
        )
    ).strip()

    if not configured_prompt:
        configured_prompt = (
            "You are a helpful Nigerian AI assistant. "
            "Be accurate, clear and culturally aware."
        )

    language_instruction = (
        LANGUAGE_INSTRUCTIONS.get(
            language,
            LANGUAGE_INSTRUCTIONS["english"],
        )
    )

    return (
        f"{configured_prompt}\n\n"
        f"{language_instruction}\n\n"
        "Follow the selected language consistently "
        "throughout your response."
    )


def get_model_name(
    project: Project,
) -> str:

    configuration = get_project_configuration(
        project
    )

    # project.model_name is the authoritative value.
    # configuration.model remains supported for older
    # projects, but only when project.model_name is empty
    # or still using the original legacy default.
    project_model = (
        project.model_name or ""
    ).strip()

    configured_model = str(
        configuration.get(
            "model",
            "",
        )
    ).strip()

    if (
        project_model
        and project_model.upper()
        not in {
            "N-ATLAS",
            "N-ATLAS 8B",
        }
    ):
        return project_model

    if configured_model:
        return configured_model

    return project_model or "NCAIR1/N-ATLaS"


@router.post(
    "/chat",
    response_model=PlaygroundResponse,
)
async def playground_chat(
    project_id: int,
    payload: PlaygroundRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):

    if project_id != payload.project_id:
        raise HTTPException(
            status_code=400,
            detail="Project ID mismatch.",
        )

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

    configuration = (
        get_project_configuration(
            project
        )
    )

    model_name = get_model_name(
        project
    )

    language = (
        payload.language
        or project.default_language
        or configuration.get(
            "default_language",
            "english",
        )
    )

    try:

        # Validate before touching the model.
        model_name = (
            NAtlasService.validate_model(
                model_name,
                capability="chat",
            )
        )

        system_prompt = build_system_prompt(
            project,
            language,
        )

        system_message = {
            "role": "system",
            "content": system_prompt,
        }

        # The backend owns the system prompt.
        #
        # This prevents the frontend from accidentally
        # overriding the project's saved behavior.
        conversation_messages = [
            system_message,
            *[
                message.model_dump()
                for message in payload.messages
                if message.role != "system"
            ],
        ]

        # Keep the Playground's live controls functional,
        # while using project configuration for runtime
        # and sampling defaults.
        configured_temperature = configuration.get(
            "temperature",
            payload.temperature,
        )

        configured_max_tokens = configuration.get(
            "max_tokens",
            payload.max_tokens,
        )

        # The current Playground still sends its live
        # temperature and max_tokens values, so those
        # remain the request-level controls.
        temperature = payload.temperature

        if payload.temperature == 0.7:
            temperature = float(
                configured_temperature
            )

        max_tokens = payload.max_tokens

        if payload.max_tokens == 512:
            max_tokens = int(
                configured_max_tokens
            )

        temperature = max(
            0.0,
            min(
                float(temperature),
                2.0,
            ),
        )

        max_tokens = max(
            1,
            min(
                int(max_tokens),
                8192,
            ),
        )

        response = await NAtlasService().chat(
            messages=conversation_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model_name=model_name,
            configuration=configuration,
        )

        content = (
            NAtlasService.extract_text(
                response["data"]
            )
        )

        experiment = Experiment(
            project_id=project.id,
            name=payload.experiment_name,
            system_prompt=system_prompt,
            user_prompt=next(
                (
                    message.content
                    for message in reversed(
                        payload.messages
                    )
                    if message.role
                    == "user"
                ),
                "",
            ),
            language=language,
            model_name=model_name,
            request_payload={
                "model": model_name,
                "messages": conversation_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "configuration": {
                    "context_size": configuration.get(
                        "context_size"
                    ),
                    "top_p": configuration.get(
                        "top_p"
                    ),
                    "top_k": configuration.get(
                        "top_k"
                    ),
                    "repetition_penalty": configuration.get(
                        "repetition_penalty"
                    ),
                    "threads": configuration.get(
                        "threads"
                    ),
                    "batch_size": configuration.get(
                        "batch_size"
                    ),
                    "gpu_layers": configuration.get(
                        "gpu_layers"
                    ),
                },
            },
            response_payload=response[
                "data"
            ],
            latency_ms=response[
                "latency_ms"
            ],
        )

        db.add(experiment)
        db.commit()
        db.refresh(experiment)

        return PlaygroundResponse(
            project_id=project.id,
            experiment_id=experiment.id,
            model=model_name,
            content=content,
            latency_ms=response[
                "latency_ms"
            ],
            provider_configured=True,
            raw_response=response[
                "data"
            ],
        )

    except NAtlasNotConfiguredError:

        return PlaygroundResponse(
            project_id=project.id,
            experiment_id=None,
            model=model_name,
            content="",
            latency_ms=0,
            provider_configured=False,
            raw_response={
                "message": (
                    "N-ATLAS provider is not configured."
                )
            },
        )

    except NAtlasRequestError as exc:

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )