# import asyncio
# import time
# from pathlib import Path

# from app.core.config import settings


# class NAtlasError(Exception):
#     pass


# class NAtlasNotConfiguredError(NAtlasError):
#     pass


# class NAtlasRequestError(NAtlasError):
#     pass


# class NAtlasService:

#     _local_model = None
#     _model_lock = None

#     def __init__(self):
#         self.base_url = settings.natlas_base_url.rstrip("/")
#         self.api_key = settings.natlas_api_key
#         self.model = settings.natlas_model
#         self.endpoint = settings.natlas_chat_endpoint

#         self.local_enabled = settings.natlas_local_enabled
#         self.model_path = Path(settings.natlas_model_path)

#     @property
#     def configured(self) -> bool:
#         if self.local_enabled:
#             return self.model_path.exists()

#         return bool(
#             self.base_url
#             and self.api_key
#         )

#     def _load_local_model(self):
#         if NAtlasService._local_model is not None:
#             return NAtlasService._local_model

#         if not self.model_path.exists():
#             raise NAtlasNotConfiguredError(
#                 f"Local N-ATLaS model was not found at: "
#                 f"{self.model_path}"
#             )

#         try:
#             from llama_cpp import Llama
#         except ImportError as exc:
#             raise NAtlasRequestError(
#                 "llama-cpp-python is not installed."
#             ) from exc

#         print(
#             f"[N-ATLaS] Loading local model: "
#             f"{self.model_path}"
#         )

#         NAtlasService._local_model = Llama(
#             model_path=str(self.model_path),
#             n_ctx=settings.natlas_context_size,
#             n_threads=settings.natlas_threads,
#             n_batch=settings.natlas_batch_size,
#             n_gpu_layers=0,
#             verbose=False,
#         )

#         print("[N-ATLaS] Local model loaded successfully.")

#         return NAtlasService._local_model

#     def _local_chat(
#         self,
#         messages: list[dict],
#         temperature: float,
#         max_tokens: int,
#     ) -> dict:

#         model = self._load_local_model()

#         started = time.perf_counter()

#         try:
#             result = model.create_chat_completion(
#                 messages=messages,
#                 temperature=temperature,
#                 max_tokens=max_tokens,
#             )

#         except Exception as exc:
#             raise NAtlasRequestError(
#                 f"Local N-ATLaS inference failed: {exc}"
#             ) from exc

#         latency_ms = (
#             time.perf_counter() - started
#         ) * 1000

#         return {
#             "data": result,
#             "latency_ms": round(
#                 latency_ms,
#                 2,
#             ),
#         }

#     async def chat(
#         self,
#         messages: list[dict],
#         temperature: float = 0.7,
#         max_tokens: int = 512,
#     ) -> dict:

#         if self.local_enabled:

#             if not self.model_path.exists():
#                 raise NAtlasNotConfiguredError(
#                     "Local N-ATLaS model was not found."
#                 )

#             return await asyncio.to_thread(
#                 self._local_chat,
#                 messages,
#                 temperature,
#                 max_tokens,
#             )

#         # Official hosted N-ATLaS API mode.
#         if not self.base_url or not self.api_key:
#             raise NAtlasNotConfiguredError(
#                 "N-ATLAS is not configured. "
#                 "Set NATLAS_BASE_URL and NATLAS_API_KEY "
#                 "using official N-ATLAS access credentials."
#             )

#         import httpx

#         url = (
#             f"{self.base_url}"
#             f"{self.endpoint}"
#         )

#         headers = {
#             "Authorization": (
#                 f"Bearer {self.api_key}"
#             ),
#             "Content-Type": "application/json",
#         }

#         payload = {
#             "model": self.model,
#             "messages": messages,
#             "temperature": temperature,
#             "max_tokens": max_tokens,
#         }

#         started = time.perf_counter()

#         try:
#             async with httpx.AsyncClient(
#                 timeout=httpx.Timeout(
#                     connect=15,
#                     read=120,
#                     write=30,
#                     pool=30,
#                 )
#             ) as client:

#                 response = await client.post(
#                     url,
#                     headers=headers,
#                     json=payload,
#                 )

#         except httpx.RequestError as exc:
#             raise NAtlasRequestError(
#                 f"Unable to reach N-ATLaS: {exc}"
#             ) from exc

#         latency_ms = (
#             time.perf_counter()
#             - started
#         ) * 1000

#         if response.status_code >= 400:
#             raise NAtlasRequestError(
#                 "N-ATLAS returned "
#                 f"HTTP {response.status_code}: "
#                 f"{response.text[:1000]}"
#             )

#         try:
#             data = response.json()

#         except ValueError as exc:
#             raise NAtlasRequestError(
#                 "N-ATLAS returned invalid JSON."
#             ) from exc

#         return {
#             "data": data,
#             "latency_ms": round(
#                 latency_ms,
#                 2,
#             ),
#         }

#     @staticmethod
#     def extract_text(
#         response: dict,
#     ) -> str:

#         choices = response.get(
#             "choices",
#             [],
#         )

#         if choices:

#             message = choices[0].get(
#                 "message",
#                 {},
#             )

#             content = message.get(
#                 "content"
#             )

#             if isinstance(
#                 content,
#                 str,
#             ):
#                 return content.strip()

#         if isinstance(
#             response.get("generated_text"),
#             str,
#         ):
#             return response[
#                 "generated_text"
#             ].strip()

#         if isinstance(
#             response.get("output"),
#             str,
#         ):
#             return response[
#                 "output"
#             ].strip()

#         return ""


import asyncio
import threading
import time
from pathlib import Path
from typing import Any

from app.core.config import settings


class NAtlasError(Exception):
    pass


class NAtlasNotConfiguredError(NAtlasError):
    pass


class NAtlasRequestError(NAtlasError):
    pass


# Official N-ATLAS model registry.
#
# The language model can be used by the Playground chat endpoint.
# The ASR models are registered here so Forge can recognize them,
# but they must use a speech/transcription workflow rather than chat.
NATLAS_MODELS = {
    "NCAIR1/N-ATLaS": {
        "name": "N-ATLaS 8B",
        "type": "language",
        "capability": "chat",
    },
    "NCAIR1/Hausa-ASR": {
        "name": "Hausa-ASR",
        "type": "speech",
        "capability": "asr",
    },
    "NCAIR1/Yoruba-ASR": {
        "name": "Yoruba-ASR",
        "type": "speech",
        "capability": "asr",
    },
    "NCAIR1/Igbo-ASR": {
        "name": "Igbo-ASR",
        "type": "speech",
        "capability": "asr",
    },
    "NCAIR1/NigerianAccentedEnglish": {
        "name": "Nigerian Accented English",
        "type": "speech",
        "capability": "asr",
    },
}


# Backwards compatibility for projects created before the model registry.
MODEL_ALIASES = {
    "N-ATLAS": "NCAIR1/N-ATLaS",
    "N-ATLaS": "NCAIR1/N-ATLaS",
    "N-ATLAS 8B": "NCAIR1/N-ATLaS",
}


class NAtlasService:

    _local_model = None
    _local_model_key = None

    # llama.cpp model objects should not be used concurrently.
    _model_lock = threading.RLock()

    def __init__(self):
        self.base_url = settings.natlas_base_url.rstrip("/")
        self.api_key = settings.natlas_api_key
        self.default_model = settings.natlas_model
        self.endpoint = settings.natlas_chat_endpoint

        self.local_enabled = settings.natlas_local_enabled

    @staticmethod
    def normalize_model_name(model_name: str | None) -> str:
        value = (model_name or "").strip()

        if not value:
            value = settings.natlas_model

        return MODEL_ALIASES.get(
            value,
            value,
        )

    @classmethod
    def get_model_info(
        cls,
        model_name: str | None,
    ) -> dict[str, Any] | None:
        normalized = cls.normalize_model_name(
            model_name
        )

        return NATLAS_MODELS.get(
            normalized
        )

    @classmethod
    def validate_model(
        cls,
        model_name: str | None,
        capability: str | None = None,
    ) -> str:

        normalized = cls.normalize_model_name(
            model_name
        )

        info = NATLAS_MODELS.get(
            normalized
        )

        if not info:
            raise NAtlasRequestError(
                f"Unsupported N-ATLAS model: "
                f"{model_name or normalized}"
            )

        if (
            capability
            and info["capability"] != capability
        ):
            raise NAtlasRequestError(
                f"Model '{normalized}' does not support "
                f"the '{capability}' capability."
            )

        return normalized

    @classmethod
    def list_models(cls) -> list[dict[str, Any]]:
        return [
            {
                "id": model_id,
                **info,
            }
            for model_id, info in NATLAS_MODELS.items()
        ]

    @property
    def configured(self) -> bool:
        if self.local_enabled:
            return bool(
                settings.natlas_model_path
                and Path(
                    settings.natlas_model_path
                ).exists()
            )

        return bool(
            self.base_url
            and self.api_key
        )

    @staticmethod
    def _get_runtime_value(
        configuration: dict | None,
        key: str,
        default: int | float,
    ):
        if not configuration:
            return default

        value = configuration.get(key)

        if value is None:
            return default

        return value

    def _get_local_model_path(
        self,
        model_name: str,
    ) -> Path:

        normalized = self.normalize_model_name(
            model_name
        )

        if normalized == "NCAIR1/N-ATLaS":
            return Path(
                settings.natlas_model_path
            )

        raise NAtlasNotConfiguredError(
            f"Local runtime for '{normalized}' "
            "is not configured yet. "
            "The ASR models require a speech runtime "
            "and model files before they can be used locally."
        )

    def _close_local_model(self):
        model = NAtlasService._local_model

        if model is None:
            return

        try:
            close_method = getattr(
                model,
                "close",
                None,
            )

            if callable(close_method):
                close_method()

        except Exception:
            # llama.cpp versions differ in how model
            # resources are released. Garbage collection
            # remains a safe fallback.
            pass

        NAtlasService._local_model = None
        NAtlasService._local_model_key = None

    def _load_local_model(
        self,
        model_name: str,
        configuration: dict | None = None,
    ):

        normalized = self.validate_model(
            model_name,
            capability="chat",
        )

        model_path = self._get_local_model_path(
            normalized
        )

        if not model_path.exists():
            raise NAtlasNotConfiguredError(
                "Local N-ATLaS model was not found at: "
                f"{model_path}"
            )

        context_size = int(
            self._get_runtime_value(
                configuration,
                "context_size",
                settings.natlas_context_size,
            )
        )

        threads = int(
            self._get_runtime_value(
                configuration,
                "threads",
                settings.natlas_threads,
            )
        )

        batch_size = int(
            self._get_runtime_value(
                configuration,
                "batch_size",
                settings.natlas_batch_size,
            )
        )

        gpu_layers = int(
            self._get_runtime_value(
                configuration,
                "gpu_layers",
                settings.natlas_gpu_layers,
            )
        )

        # Prevent obviously invalid runtime values.
        context_size = max(
            512,
            min(context_size, 32768),
        )

        threads = max(
            1,
            min(threads, 64),
        )

        batch_size = max(
            1,
            min(batch_size, 4096),
        )

        gpu_layers = max(
            0,
            min(gpu_layers, 999),
        )

        model_key = (
            str(model_path.resolve()),
            context_size,
            threads,
            batch_size,
            gpu_layers,
        )

        if (
            NAtlasService._local_model is not None
            and NAtlasService._local_model_key
            == model_key
        ):
            return NAtlasService._local_model

        # Runtime settings changed. Replace the old
        # llama.cpp instance rather than continuing to
        # use stale settings.
        self._close_local_model()

        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise NAtlasRequestError(
                "llama-cpp-python is not installed."
            ) from exc

        print(
            "[N-ATLaS] Loading local model: "
            f"{model_path}"
        )

        print(
            "[N-ATLaS] Runtime: "
            f"context={context_size}, "
            f"threads={threads}, "
            f"batch={batch_size}, "
            f"gpu_layers={gpu_layers}"
        )

        try:
            NAtlasService._local_model = Llama(
                model_path=str(model_path),
                n_ctx=context_size,
                n_threads=threads,
                n_batch=batch_size,
                n_gpu_layers=gpu_layers,
                verbose=False,
            )

        except Exception as exc:
            NAtlasService._local_model = None
            NAtlasService._local_model_key = None

            raise NAtlasRequestError(
                "Unable to load local N-ATLaS model: "
                f"{exc}"
            ) from exc

        NAtlasService._local_model_key = (
            model_key
        )

        print(
            "[N-ATLaS] Local model loaded successfully."
        )

        return NAtlasService._local_model

    def _local_chat(
        self,
        model_name: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        configuration: dict | None = None,
    ) -> dict:

        started = time.perf_counter()

        top_p = float(
            self._get_runtime_value(
                configuration,
                "top_p",
                0.95,
            )
        )

        top_k = int(
            self._get_runtime_value(
                configuration,
                "top_k",
                40,
            )
        )

        repetition_penalty = float(
            self._get_runtime_value(
                configuration,
                "repetition_penalty",
                1.1,
            )
        )

        top_p = max(
            0.0,
            min(top_p, 1.0),
        )

        top_k = max(
            0,
            min(top_k, 200),
        )

        repetition_penalty = max(
            0.5,
            min(
                repetition_penalty,
                2.0,
            ),
        )

        with NAtlasService._model_lock:

            model = self._load_local_model(
                model_name=model_name,
                configuration=configuration,
            )

            try:
                result = model.create_chat_completion(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    top_k=top_k,
                    repeat_penalty=repetition_penalty,
                )

            except Exception as exc:
                raise NAtlasRequestError(
                    "Local N-ATLaS inference failed: "
                    f"{exc}"
                ) from exc

        latency_ms = (
            time.perf_counter()
            - started
        ) * 1000

        return {
            "data": result,
            "latency_ms": round(
                latency_ms,
                2,
            ),
            "provider": "LOCAL",
            "local": True,
            "model": self.normalize_model_name(
                model_name
            ),
        }

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 512,
        model_name: str | None = None,
        configuration: dict | None = None,
    ) -> dict:

        selected_model = (
            model_name
            or self.default_model
        )

        selected_model = self.validate_model(
            selected_model,
            capability="chat",
        )

        temperature = max(
            0.0,
            min(float(temperature), 2.0),
        )

        max_tokens = max(
            1,
            min(int(max_tokens), 8192),
        )

        if self.local_enabled:

            model_path = (
                self._get_local_model_path(
                    selected_model
                )
            )

            if not model_path.exists():
                raise NAtlasNotConfiguredError(
                    "Local N-ATLaS model was not found at: "
                    f"{model_path}"
                )

            return await asyncio.to_thread(
                self._local_chat,
                selected_model,
                messages,
                temperature,
                max_tokens,
                configuration,
            )

        # Official hosted N-ATLaS API mode.
        if not self.base_url or not self.api_key:
            raise NAtlasNotConfiguredError(
                "N-ATLAS is not configured. "
                "Set NATLAS_BASE_URL and NATLAS_API_KEY "
                "using official N-ATLAS access credentials."
            )

        import httpx

        url = (
            f"{self.base_url}"
            f"{self.endpoint}"
        )

        headers = {
            "Authorization": (
                f"Bearer {self.api_key}"
            ),
            "Content-Type": "application/json",
        }

        # Keep the hosted request compatible with the
        # existing OpenAI-style N-ATLAS endpoint.
        payload = {
            "model": selected_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # top_p is supported by common OpenAI-compatible
        # chat endpoints and is safe to forward when configured.
        if configuration:
            top_p = configuration.get(
                "top_p"
            )

            if top_p is not None:
                payload["top_p"] = max(
                    0.0,
                    min(float(top_p), 1.0),
                )

        started = time.perf_counter()

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=15,
                    read=120,
                    write=30,
                    pool=30,
                )
            ) as client:

                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                )

        except httpx.RequestError as exc:
            raise NAtlasRequestError(
                f"Unable to reach N-ATLaS: {exc}"
            ) from exc

        latency_ms = (
            time.perf_counter()
            - started
        ) * 1000

        if response.status_code >= 400:
            raise NAtlasRequestError(
                "N-ATLAS returned "
                f"HTTP {response.status_code}: "
                f"{response.text[:1000]}"
            )

        try:
            data = response.json()

        except ValueError as exc:
            raise NAtlasRequestError(
                "N-ATLAS returned invalid JSON."
            ) from exc

        return {
            "data": data,
            "latency_ms": round(
                latency_ms,
                2,
            ),
            "provider": "N-ATLAS",
            "local": False,
            "model": selected_model,
        }

    @staticmethod
    def extract_text(
        response: dict,
    ) -> str:

        choices = response.get(
            "choices",
            [],
        )

        if choices:

            message = choices[0].get(
                "message",
                {},
            )

            content = message.get(
                "content"
            )

            if isinstance(
                content,
                str,
            ):
                return content.strip()

            # Some inference servers return
            # structured content arrays.
            if isinstance(
                content,
                list,
            ):
                text_parts = []

                for item in content:
                    if isinstance(
                        item,
                        str,
                    ):
                        text_parts.append(
                            item
                        )

                    elif isinstance(
                        item,
                        dict,
                    ):
                        text_value = item.get(
                            "text"
                        )

                        if isinstance(
                            text_value,
                            str,
                        ):
                            text_parts.append(
                                text_value
                            )

                if text_parts:
                    return "\n".join(
                        text_parts
                    ).strip()

        if isinstance(
            response.get("generated_text"),
            str,
        ):
            return response[
                "generated_text"
            ].strip()

        if isinstance(
            response.get("output"),
            str,
        ):
            return response[
                "output"
            ].strip()

        return ""