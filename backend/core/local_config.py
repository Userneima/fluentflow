"""Local backend-owned configuration for sensitive FluentFlow settings."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from backend.core.runtime_paths import default_config_path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = default_config_path()
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"

SENSITIVE_FIELDS = {
    "deepseek_api_key",
    "openai_api_key",
    "dashscope_api_key",
    "qwen_api_key",
    "lark_app_id",
    "lark_app_secret",
    "pyannote_auth_token",
    "elevenlabs_api_key",
    "azure_speech_key",
    "azure_speech_endpoint",
    "azure_blob_container_sas_url",
}

ENV_FALLBACKS = {
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "dashscope_api_key": "DASHSCOPE_API_KEY",
    "qwen_api_key": "QWEN_API_KEY",
    "lark_app_id": "LARK_APP_ID",
    "lark_app_secret": "LARK_APP_SECRET",
    "pyannote_auth_token": "PYANNOTE_AUTH_TOKEN",
    "elevenlabs_api_key": "ELEVENLABS_API_KEY",
    "azure_speech_key": "AZURE_SPEECH_KEY",
    "azure_speech_endpoint": "AZURE_SPEECH_ENDPOINT",
    "azure_blob_container_sas_url": "AZURE_BLOB_CONTAINER_SAS_URL",
}

SECRET_ALIASES = {
    "dashscope_api_key": ("dashscope_api_key", "qwen_api_key"),
    "qwen_api_key": ("qwen_api_key", "dashscope_api_key"),
}

ENV_ALIAS_FALLBACKS = {
    "dashscope_api_key": ("DASHSCOPE_API_KEY", "QWEN_API_KEY"),
    "qwen_api_key": ("QWEN_API_KEY", "DASHSCOPE_API_KEY"),
}


def load_project_env() -> None:
    if DEFAULT_ENV_PATH.exists():
        load_dotenv(DEFAULT_ENV_PATH, override=False)


def config_path() -> Path:
    override = os.environ.get("FLUENTFLOW_CONFIG_PATH")
    return Path(override).expanduser() if override else DEFAULT_CONFIG_PATH


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    target = Path(path) if path else config_path()
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_sensitive_settings(patch: dict[str, Any], path: Path | str | None = None) -> dict[str, Any]:
    target = Path(path) if path else config_path()
    current = load_config(target)
    secrets = current.get("secrets") if isinstance(current.get("secrets"), dict) else {}
    next_secrets = dict(secrets)
    for key in SENSITIVE_FIELDS:
        if key not in patch:
            continue
        value = patch.get(key)
        if value is None or str(value) == "":
            next_secrets.pop(key, None)
        else:
            next_secrets[key] = str(value)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"secrets": next_secrets}, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return credential_status(path=target)


def get_sensitive_setting(name: str, path: Path | str | None = None) -> str | None:
    if name not in SENSITIVE_FIELDS:
        return None
    if path is None:
        load_project_env()
    data = load_config(path)
    secrets = data.get("secrets") if isinstance(data.get("secrets"), dict) else {}
    for secret_name in SECRET_ALIASES.get(name, (name,)):
        value = (secrets.get(secret_name) or "").strip()
        if value:
            return value
    env_names = ENV_ALIAS_FALLBACKS.get(name, (ENV_FALLBACKS.get(name),))
    for env_name in env_names:
        if not env_name:
            continue
        env_value = (os.environ.get(env_name) or "").strip()
        if env_value:
            return env_value
    return None


def credential_status(path: Path | str | None = None) -> dict[str, Any]:
    return {
        "deepseek_api_key_configured": bool(get_sensitive_setting("deepseek_api_key", path)),
        "openai_api_key_configured": bool(get_sensitive_setting("openai_api_key", path)),
        "dashscope_api_key_configured": bool(get_sensitive_setting("dashscope_api_key", path)),
        "qwen_api_key_configured": bool(get_sensitive_setting("qwen_api_key", path)),
        "lark_app_id_configured": bool(get_sensitive_setting("lark_app_id", path)),
        "lark_app_secret_configured": bool(get_sensitive_setting("lark_app_secret", path)),
        "pyannote_auth_token_configured": bool(get_sensitive_setting("pyannote_auth_token", path)),
        "elevenlabs_api_key_configured": bool(get_sensitive_setting("elevenlabs_api_key", path)),
        "azure_speech_key_configured": bool(get_sensitive_setting("azure_speech_key", path)),
        "azure_speech_endpoint_configured": bool(get_sensitive_setting("azure_speech_endpoint", path)),
        "azure_blob_container_sas_url_configured": bool(get_sensitive_setting("azure_blob_container_sas_url", path)),
        "storage": "backend_local_file",
    }


def resolve_secret(form_value: str | None, name: str) -> str | None:
    value = (form_value or "").strip()
    if value:
        return value
    return get_sensitive_setting(name)
