from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from backend.core import local_config
from backend.core.local_config import credential_status, resolve_secret, save_sensitive_settings


def test_sensitive_settings_are_saved_server_side(tmp_path: Path) -> None:
    path = tmp_path / "config.json"

    status = save_sensitive_settings(
        {
            "deepseek_api_key": "ds-key",
            "lark_app_secret": "lark-secret",
            "azure_speech_key": "azure-key",
            "azure_speech_endpoint": "https://eastasia.api.cognitive.microsoft.com",
            "azure_blob_container_sas_url": "https://example.blob.core.windows.net/fluentflow?sp=rcw",
        },
        path=path,
    )

    assert status["deepseek_api_key_configured"] is True
    assert status["lark_app_secret_configured"] is True
    assert status["azure_speech_key_configured"] is True
    assert status["azure_speech_endpoint_configured"] is True
    assert status["azure_blob_container_sas_url_configured"] is True
    with patch.dict(os.environ, {}, clear=True):
        assert resolve_secret(None, "unknown") is None


def test_resolve_secret_prefers_form_value_then_env(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    save_sensitive_settings({"openai_api_key": "stored-openai"}, path=path)

    with patch.dict(os.environ, {"OPENAI_API_KEY": "env-openai"}, clear=False):
        assert resolve_secret("form-openai", "openai_api_key") == "form-openai"

    status = credential_status(path=path)
    assert status["openai_api_key_configured"] is True


def test_credentials_load_project_env_when_no_config_path(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("DEEPSEEK_API_KEY=env-deepseek\nLARK_APP_ID=env-lark\n", encoding="utf-8")
    monkeypatch.setattr(local_config, "DEFAULT_ENV_PATH", env_path)
    monkeypatch.setenv("FLUENTFLOW_CONFIG_PATH", str(tmp_path / "missing.json"))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("LARK_APP_ID", raising=False)

    status = credential_status()

    assert status["deepseek_api_key_configured"] is True
    assert status["lark_app_id_configured"] is True
