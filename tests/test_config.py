import pytest
from pydantic import ValidationError

from core.config import AppSettings, ModelSettings, Settings


def test_defaults_are_local_first():
    settings = Settings(_env_file=None)
    assert settings.app.engine == "faster-whisper"
    assert settings.model.size == "large-v3-turbo"
    assert settings.device == "cpu"
    assert settings.resolved_compute_type == "int8"
    assert settings.post.provider == "none"
    assert settings.diarizer_model == "pyannote/speaker-diarization-3.1"
    assert settings.job.workers == 2


@pytest.mark.parametrize("size", ["xl-2", "", "large-4"])
def test_invalid_model_size_is_rejected(size):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, model=ModelSettings(size=size))


def test_invalid_engine_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app=AppSettings(engine="magic"))


def test_cuda_resolves_float16():
    settings = Settings(_env_file=None, device="cuda")
    assert settings.resolved_compute_type == "float16"


def test_explicit_int8_on_cuda_is_coerced_to_float16():
    settings = Settings(_env_file=None, device="cuda", compute_type="int8")
    assert settings.resolved_compute_type == "float16"


def test_float16_on_cpu_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, device="cpu", compute_type="float16")


def test_invalid_post_provider_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, post={"provider": "skynet"})


def test_nested_env_overrides(monkeypatch):
    monkeypatch.setenv("APP__ENGINE", "openai-whisper")
    monkeypatch.setenv("MODEL__SIZE", "small")
    monkeypatch.setenv("DEVICE", "cuda")
    monkeypatch.setenv("HUGGINGFACE_TOKEN", "hf_test")
    monkeypatch.setenv("JOB__WORKERS", "3")
    settings = Settings(_env_file=None)
    assert settings.app.engine == "openai-whisper"
    assert settings.model.size == "small"
    assert settings.resolved_compute_type == "float16"
    assert settings.diarization_enabled is True
    assert settings.job.workers == 3


def test_invalid_compute_type_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, compute_type="bfloat16")


def test_ensure_media_dir(tmp_path):
    settings = Settings(_env_file=None, media={"dir": tmp_path / "media"})
    created = settings.ensure_media_dir()
    assert created.is_dir()
