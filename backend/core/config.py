"""Application settings (pydantic-settings).

Every value can be overridden with environment variables or a local ``.env``.
Nested sections use the ``__`` delimiter, e.g. ``APP__ENGINE`` or ``JOB__WORKERS``.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENGINE_CHOICES = ("faster-whisper", "openai-whisper", "cloud-transcribe")
POST_PROVIDERS = ("none", "ollama", "openai")
DEVICE_CHOICES = ("cpu", "cuda")
COMPUTE_TYPES = ("int8", "float16", "float32", "int8_float16")
MODEL_SIZES = (
    "tiny",
    "tiny.en",
    "base",
    "base.en",
    "small",
    "small.en",
    "medium",
    "medium.en",
    "large-v1",
    "large-v2",
    "large-v3",
    "large-v3-turbo",
    "distil-large-v3",
)


class AppSettings(BaseModel):
    engine: str = "faster-whisper"

    @field_validator("engine")
    @classmethod
    def _validate_engine(cls, value: str) -> str:
        if value not in ENGINE_CHOICES:
            raise ValueError(f"engine must be one of {ENGINE_CHOICES}, got {value!r}")
        return value


class ModelSettings(BaseModel):
    size: str = "large-v3-turbo"

    @field_validator("size")
    @classmethod
    def _validate_size(cls, value: str) -> str:
        if value not in MODEL_SIZES:
            raise ValueError(
                f"model size must be one of {', '.join(MODEL_SIZES)}, got {value!r}"
            )
        return value


class PostSettings(BaseModel):
    provider: str = "none"

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, value: str) -> str:
        if value not in POST_PROVIDERS:
            raise ValueError(f"post provider must be one of {POST_PROVIDERS}, got {value!r}")
        return value


class OllamaSettings(BaseModel):
    base_url: str = "http://localhost:11434"
    model: str = "llama3.1"
    timeout_s: float = 60.0


class CloudSettings(BaseModel):
    api_key: str = ""
    model: str = "gpt-4o-transcribe"


class MediaSettings(BaseModel):
    dir: Path = Path("./media")


class JobSettings(BaseModel):
    workers: int = Field(default=2, ge=1, le=8)


class SseSettings(BaseModel):
    enabled: bool = True


class Settings(BaseSettings):
    """Root settings object.

    ``Settings(_env_file=None)`` builds a hermetic object ignoring any local
    ``.env`` — tests rely on that to assert defaults.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    app: AppSettings = Field(default_factory=AppSettings)
    model: ModelSettings = Field(default_factory=ModelSettings)
    device: str = "cpu"
    compute_type: str | None = None
    huggingface_token: str = ""
    diarizer_model: str = "pyannote/speaker-diarization-3.1"
    post: PostSettings = Field(default_factory=PostSettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    cloud: CloudSettings = Field(default_factory=CloudSettings)
    media: MediaSettings = Field(default_factory=MediaSettings)
    job: JobSettings = Field(default_factory=JobSettings)
    sse: SseSettings = Field(default_factory=SseSettings)
    max_upload_mb: int = Field(default=512, ge=1)

    @field_validator("device")
    @classmethod
    def _validate_device(cls, value: str) -> str:
        if value not in DEVICE_CHOICES:
            raise ValueError(f"device must be one of {DEVICE_CHOICES}, got {value!r}")
        return value

    @field_validator("compute_type")
    @classmethod
    def _validate_compute_type(cls, value: str | None) -> str | None:
        if value is not None and value not in COMPUTE_TYPES:
            raise ValueError(f"compute_type must be one of {COMPUTE_TYPES}, got {value!r}")
        return value

    @model_validator(mode="after")
    def _validate_device_compute_pair(self) -> "Settings":
        if self.device == "cpu" and self.compute_type == "float16":
            raise ValueError("compute_type=float16 requires device=cuda")
        if self.device == "cuda" and self.compute_type == "int8":
            # Explicit int8 on GPU is valid in ctranslate2 but the spec wants float16.
            self.compute_type = "float16"
        return self

    @property
    def resolved_compute_type(self) -> str:
        if self.compute_type:
            return self.compute_type
        return "float16" if self.device == "cuda" else "int8"

    @property
    def diarization_enabled(self) -> bool:
        return bool(self.huggingface_token.strip())

    def ensure_media_dir(self) -> Path:
        directory = Path(self.media.dir).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        return directory
