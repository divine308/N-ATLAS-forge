import asyncio
import gc
import threading
import time
from pathlib import Path
from typing import Any

from app.core.config import settings


class NAtlasASRError(Exception):
    pass


class NAtlasASRNotConfiguredError(
    NAtlasASRError
):
    pass


class NAtlasASRRequestError(
    NAtlasASRError
):
    pass


NATLAS_ASR_MODELS = {
    "NCAIR1/Hausa-ASR": {
        "name": "Hausa-ASR",
        "language": "hausa",
        "language_code": "ha",
    },
    "NCAIR1/Yoruba-ASR": {
        "name": "Yoruba-ASR",
        "language": "yoruba",
        "language_code": "yo",
    },
    "NCAIR1/Igbo-ASR": {
        "name": "Igbo-ASR",
        "language": "igbo",
        "language_code": "ig",
    },
    "NCAIR1/NigerianAccentedEnglish": {
        "name": "Nigerian Accented English",
        "language": "english",
        "language_code": "en",
    },
}


class NAtlasASRService:

    _pipeline = None
    _loaded_model = None
    _pipeline_lock = threading.RLock()

    def __init__(self):
        self.hf_token = (
            settings.hf_token.strip()
        )

        self.cache_dir = Path(
            settings.asr_cache_dir
        )

        self.device = (
            settings.asr_device
            .strip()
            .lower()
        )

        self.sample_rate = (
            settings.asr_sample_rate
        )

        self.chunk_length_s = (
            settings.asr_chunk_length_s
        )

        self.stride_length_s = (
            settings.asr_stride_length_s
        )

        self.max_audio_size_mb = (
            settings.asr_max_audio_size_mb
        )

    @classmethod
    def validate_model(
        cls,
        model_name: str,
    ) -> str:

        model_name = (
            model_name or ""
        ).strip()

        if model_name not in NATLAS_ASR_MODELS:
            raise NAtlasASRRequestError(
                "Unsupported N-ATLAS ASR model: "
                f"{model_name}"
            )

        return model_name

    @classmethod
    def list_models(
        cls,
    ) -> list[dict[str, Any]]:

        return [
            {
                "id": model_id,
                **info,
            }
            for model_id, info
            in NATLAS_ASR_MODELS.items()
        ]

    @property
    def configured(self) -> bool:
        return bool(
            self.hf_token
        )

    def _check_configuration(self):

        if not self.hf_token:
            raise NAtlasASRNotConfiguredError(
                "N-ATLAS ASR is not configured. "
                "Set HF_TOKEN in the backend .env file "
                "and make sure your Hugging Face account "
                "has access to the official N-ATLAS ASR models."
            )

        self.cache_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    def _load_pipeline(
        self,
        model_name: str,
    ):

        model_name = self.validate_model(
            model_name
        )

        self._check_configuration()

        with self._pipeline_lock:

            # Reuse the currently loaded model.
            if (
                self._pipeline is not None
                and self._loaded_model
                == model_name
            ):
                return self._pipeline

            # Only keep one ASR model in memory.
            self._unload_pipeline()

            try:
                from transformers import (
                    pipeline,
                )
            except ImportError as exc:
                raise NAtlasASRRequestError(
                    "Transformers is not installed. "
                    "Run: pip install transformers accelerate"
                ) from exc

            device = (
                0
                if self.device
                in {
                    "cuda",
                    "gpu",
                }
                else -1
            )

            print(
                "[N-ATLaS ASR] Loading model: "
                f"{model_name}"
            )

            print(
                "[N-ATLaS ASR] Device: "
                f"{self.device}"
            )

            try:
                self._pipeline = pipeline(
                    "automatic-speech-recognition",
                    model=model_name,
                    token=self.hf_token,
                    cache_dir=str(
                        self.cache_dir
                    ),
                    device=device,
                )

            except Exception as exc:
                self._pipeline = None
                self._loaded_model = None

                raise NAtlasASRRequestError(
                    "Unable to load N-ATLAS ASR model "
                    f"'{model_name}': {exc}"
                ) from exc

            self._loaded_model = (
                model_name
            )

            print(
                "[N-ATLaS ASR] Model loaded successfully."
            )

            return self._pipeline

    def _unload_pipeline(self):

        if self._pipeline is None:
            return

        self._pipeline = None
        self._loaded_model = None

        gc.collect()

        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        except Exception:
            pass

    @staticmethod
    def _validate_audio_bytes(
        audio_bytes: bytes,
        filename: str | None,
    ):

        if not audio_bytes:
            raise NAtlasASRRequestError(
                "The uploaded audio file is empty."
            )

        max_bytes = (
            settings.asr_max_audio_size_mb
            * 1024
            * 1024
        )

        if len(audio_bytes) > max_bytes:
            raise NAtlasASRRequestError(
                "Audio file is too large. "
                f"Maximum size is "
                f"{settings.asr_max_audio_size_mb} MB."
            )

        if filename:
            extension = (
                Path(filename)
                .suffix
                .lower()
            )

            allowed_extensions = {
                ".wav",
                ".mp3",
                ".m4a",
                ".flac",
                ".ogg",
                ".webm",
                ".aac",
                ".mp4",
            }

            if extension and (
                extension
                not in allowed_extensions
            ):
                raise NAtlasASRRequestError(
                    "Unsupported audio format: "
                    f"{extension}. "
                    "Supported formats include WAV, MP3, M4A, "
                    "FLAC, OGG, WebM and AAC."
                )

    @staticmethod
    def _decode_audio(
        audio_bytes: bytes,
    ):

        try:
            import io

            import librosa

        except ImportError as exc:
            raise NAtlasASRRequestError(
                "Audio dependencies are missing. "
                "Install librosa and soundfile."
            ) from exc

        try:
            audio, sample_rate = (
                librosa.load(
                    io.BytesIO(
                        audio_bytes
                    ),
                    sr=settings.asr_sample_rate,
                    mono=True,
                )
            )

        except Exception as exc:
            raise NAtlasASRRequestError(
                "Unable to decode the audio file. "
                "Make sure the file is a valid audio recording."
            ) from exc

        if audio is None:
            raise NAtlasASRRequestError(
                "No audio waveform was found."
            )

        if len(audio) == 0:
            raise NAtlasASRRequestError(
                "The audio recording contains no samples."
            )

        return audio, sample_rate

    def _transcribe_sync(
        self,
        model_name: str,
        audio_bytes: bytes,
        filename: str | None = None,
    ) -> dict:

        started = time.perf_counter()

        self._validate_audio_bytes(
            audio_bytes,
            filename,
        )

        audio, sample_rate = (
            self._decode_audio(
                audio_bytes
            )
        )

        asr = self._load_pipeline(
            model_name
        )

        model_info = (
            NATLAS_ASR_MODELS[
                model_name
            ]
        )

        language_code = (
            model_info[
                "language_code"
            ]
        )

        try:
            result = asr(
                {
                    "raw": audio,
                    "sampling_rate": sample_rate,
                },
                chunk_length_s=(
                    self.chunk_length_s
                ),
                stride_length_s=(
                    self.stride_length_s
                ),
                generate_kwargs={
                    "task": "transcribe",
                    "language": language_code,
                },
            )

        except TypeError:
            # Some installed Transformers versions
            # do not accept all kwargs through pipeline.
            try:
                result = asr(
                    {
                        "raw": audio,
                        "sampling_rate": sample_rate,
                    },
                    chunk_length_s=(
                        self.chunk_length_s
                    ),
                    stride_length_s=(
                        self.stride_length_s
                    ),
                )

            except Exception as exc:
                raise NAtlasASRRequestError(
                    "N-ATLAS ASR transcription failed: "
                    f"{exc}"
                ) from exc

        except Exception as exc:
            raise NAtlasASRRequestError(
                "N-ATLAS ASR transcription failed: "
                f"{exc}"
            ) from exc

        text = ""

        if isinstance(
            result,
            dict,
        ):
            text = result.get(
                "text",
                "",
            )

        elif isinstance(
            result,
            str,
        ):
            text = result

        if not isinstance(
            text,
            str,
        ):
            text = str(text)

        text = text.strip()

        if not text:
            raise NAtlasASRRequestError(
                "N-ATLAS ASR completed but returned "
                "an empty transcription."
            )

        duration_seconds = (
            len(audio)
            / sample_rate
        )

        latency_ms = (
            time.perf_counter()
            - started
        ) * 1000

        return {
            "text": text,
            "model": model_name,
            "model_name": model_info[
                "name"
            ],
            "language": model_info[
                "language"
            ],
            "language_code": language_code,
            "sample_rate": sample_rate,
            "duration_seconds": round(
                duration_seconds,
                2,
            ),
            "latency_ms": round(
                latency_ms,
                2,
            ),
            "provider": "N-ATLAS",
            "local": True,
        }

    async def transcribe(
        self,
        model_name: str,
        audio_bytes: bytes,
        filename: str | None = None,
    ) -> dict:

        model_name = self.validate_model(
            model_name
        )

        return await asyncio.to_thread(
            self._transcribe_sync,
            model_name,
            audio_bytes,
            filename,
        )

    @classmethod
    def unload(cls):
        with cls._pipeline_lock:
            if cls._pipeline is not None:
                cls._pipeline = None
                cls._loaded_model = None

            gc.collect()

            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

            except Exception:
                pass