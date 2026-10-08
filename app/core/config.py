# # from functools import lru_cache

# # from pydantic_settings import (
# #     BaseSettings,
# #     SettingsConfigDict,
# # )


# # class Settings(BaseSettings):

# #     app_name: str = "N-ATLAS Forge"
# #     app_env: str = "development"
# #     debug: bool = True

# #     database_url: str = "sqlite:///./natlas_forge.db"

# #     jwt_secret_key: str = "change-me"
# #     jwt_algorithm: str = "HS256"
# #     access_token_expire_minutes: int = 1440

# #     frontend_url: str = "http://localhost:5173"

# #     # Official hosted N-ATLaS configuration.
# #     natlas_base_url: str = ""
# #     natlas_api_key: str = ""
# #     natlas_model: str = "N-ATLaS"
# #     natlas_chat_endpoint: str = "/v1/chat/completions"

# #     # Local N-ATLaS configuration.
# #     natlas_local_enabled: bool = True

# #     natlas_model_path: str = (
# #         "./N-ATLaS-GGUF-Q4_K_M.gguf"
# #     )

# #     # Conservative settings for the 8 GB laptop.
# #     natlas_context_size: int = 4096
# #     natlas_threads: int = 4
# #     natlas_batch_size: int = 128

# #     max_dataset_size_mb: int = 25
# #     max_dataset_records: int = 10000

# #     model_config = SettingsConfigDict(
# #         env_file=".env",
# #         env_file_encoding="utf-8",
# #         case_sensitive=False,
# #         extra="ignore",
# #     )


# # @lru_cache
# # def get_settings() -> Settings:
# #     return Settings()


# # settings = get_settings()

# from functools import lru_cache

# from pydantic_settings import (
#     BaseSettings,
#     SettingsConfigDict,
# )


# class Settings(BaseSettings):

#     app_name: str = "N-ATLAS Forge"
#     app_env: str = "development"
#     debug: bool = True

#     database_url: str = "sqlite:///./natlas_forge.db"

#     jwt_secret_key: str = "change-me"
#     jwt_algorithm: str = "HS256"
#     access_token_expire_minutes: int = 1440

#     frontend_url: str = "http://localhost:5173"

#     # Official hosted N-ATLaS configuration.
#     natlas_base_url: str = ""
#     natlas_api_key: str = ""
#     natlas_model: str = "NCAIR1/N-ATLaS"
#     natlas_chat_endpoint: str = "/v1/chat/completions"

#     # Local N-ATLaS configuration.
#     natlas_local_enabled: bool = True

#     natlas_model_path: str = (
#         "./N-ATLaS-GGUF-Q4_K_M.gguf"
#     )

#     # Conservative defaults for the 8 GB laptop.
#     #
#     # These values are used when a project does not
#     # provide its own runtime configuration.
#     natlas_context_size: int = 4096
#     natlas_threads: int = 4
#     natlas_batch_size: int = 128
#     natlas_gpu_layers: int = 0

#     max_dataset_size_mb: int = 25
#     max_dataset_records: int = 10000

#     model_config = SettingsConfigDict(
#         env_file=".env",
#         env_file_encoding="utf-8",
#         case_sensitive=False,
#         extra="ignore",
#     )


# @lru_cache
# def get_settings() -> Settings:
#     return Settings()


# settings = get_settings()

from functools import lru_cache

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):

    app_name: str = "N-ATLAS Forge"
    app_env: str = "development"
    debug: bool = True

    database_url: str = "sqlite:///./natlas_forge.db"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    frontend_url: str = "http://localhost:5173"

    # ---------------------------------------------------------
    # Hosted N-ATLaS
    # ---------------------------------------------------------

    natlas_base_url: str = ""
    natlas_api_key: str = ""
    natlas_model: str = "NCAIR1/N-ATLaS"
    natlas_chat_endpoint: str = "/v1/chat/completions"

    # ---------------------------------------------------------
    # Local N-ATLaS
    # ---------------------------------------------------------

    natlas_local_enabled: bool = True

    natlas_model_path: str = (
        "./N-ATLaS-GGUF-Q4_K_M.gguf"
    )

    natlas_context_size: int = 4096
    natlas_threads: int = 4
    natlas_batch_size: int = 128
    natlas_gpu_layers: int = 0

    # ---------------------------------------------------------
    # N-ATLAS ASR
    # ---------------------------------------------------------

    # Hugging Face token required because the official
    # N-ATLAS ASR repositories are gated.
    hf_token: str = ""

    # Where Transformers/Hugging Face stores downloaded models.
    asr_cache_dir: str = "./models/asr"

    # CPU is the safest default for Forge development.
    # Set to "cuda" when a compatible CUDA/PyTorch setup exists.
    asr_device: str = "cpu"

    # Whisper Small is approximately 244M parameters.
    # Loading one model at a time is intentional so that
    # an 8 GB development machine does not attempt to keep
    # four ASR models in memory simultaneously.
    asr_max_audio_size_mb: int = 25

    # Official model cards recommend 16 kHz audio.
    asr_sample_rate: int = 16000

    # Whisper context is approximately 30 seconds.
    asr_chunk_length_s: int = 30

    # Small overlap helps preserve words crossing chunk boundaries.
    asr_stride_length_s: int = 5

    max_dataset_size_mb: int = 25
    max_dataset_records: int = 10000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()