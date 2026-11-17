from pathlib import Path

import pytest

from praxis.config import (
    API_KEY_PLACEHOLDER,
    DEFAULT_DATABASE_PATH,
    DEFAULT_MODEL,
    ConfigError,
    load_settings,
)


def test_defaults_apply_when_nothing_is_configured():
    settings = load_settings(env={})

    assert settings.openai_api_key is None
    assert settings.openai_model == DEFAULT_MODEL
    assert settings.openai_base_url is None
    assert settings.database_path == DEFAULT_DATABASE_PATH


def test_configured_values_are_used():
    settings = load_settings(
        env={
            "OPENAI_API_KEY": "  test-key  ",
            "OPENAI_MODEL": "some-model",
            "OPENAI_BASE_URL": "http://localhost:1234/v1",
            "PRAXIS_DATABASE_PATH": "tmp/x.db",
        }
    )

    assert settings.require_api_key() == "test-key"
    assert settings.openai_model == "some-model"
    assert settings.openai_base_url == "http://localhost:1234/v1"
    assert settings.database_path == Path("tmp/x.db")


@pytest.mark.parametrize("value", ["", "   ", API_KEY_PLACEHOLDER])
def test_missing_or_placeholder_key_is_rejected_on_demand(value):
    settings = load_settings(env={"OPENAI_API_KEY": value})

    assert settings.openai_api_key is None
    with pytest.raises(ConfigError, match=".env.example"):
        settings.require_api_key()


def test_env_file_is_read(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=from-file\nOPENAI_MODEL=file-model\n")

    settings = load_settings(env_file=env_file)

    assert settings.openai_api_key == "from-file"
    assert settings.openai_model == "file-model"


def test_process_environment_overrides_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_MODEL=file-model\n")
    monkeypatch.setenv("OPENAI_MODEL", "env-model")

    assert load_settings(env_file=env_file).openai_model == "env-model"
