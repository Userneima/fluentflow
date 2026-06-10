from __future__ import annotations

from pathlib import Path

import backend.core.local_config as local_config
import scripts.check_deployment_readiness as deployment_readiness
from scripts.check_deployment_readiness import run_checks


SECRET_ENV_KEYS = (
    "FLUENTFLOW_PUBLIC_MODE",
    "FLUENTFLOW_AUTH_MODE",
    "FLUENTFLOW_ACCOUNT_AUTH",
    "FLUENTFLOW_ALLOW_SIGNUPS",
    "FLUENTFLOW_ACCOUNT_DB_PATH",
    "FLUENTFLOW_ACCESS_TOKEN",
    "FLUENTFLOW_ACCESS_TOKENS",
    "FLUENTFLOW_ALLOWED_STT_PROVIDERS",
    "FLUENTFLOW_DEFAULT_STT_PROVIDER",
    "AZURE_SPEECH_ENDPOINT",
    "AZURE_SPEECH_KEY",
    "AZURE_BLOB_CONTAINER_SAS_URL",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "LARK_APP_ID",
    "LARK_APP_SECRET",
    "FLUENTFLOW_SOURCE_DIR",
    "FLUENTFLOW_ARTIFACT_DIR",
    "FLUENTFLOW_EDITED_TRANSCRIPT_DIR",
    "FLUENTFLOW_TRANSCRIPT_EDIT_RECORDS_DIR",
    "FLUENTFLOW_VIDEO_SOURCE_DIR",
)


def _clear_env(monkeypatch) -> None:
    for key in SECRET_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _isolate_machine_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(local_config, "DEFAULT_ENV_PATH", tmp_path / ".env")
    monkeypatch.setenv("FLUENTFLOW_CONFIG_PATH", str(tmp_path / "fluentflow_config.json"))

    def fake_which(name: str):
        if name in {"ffmpeg", "ffprobe"}:
            return f"/usr/bin/{name}"
        return None

    monkeypatch.setattr(deployment_readiness.shutil, "which", fake_which)


def _set_storage_dirs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("FLUENTFLOW_EDITED_TRANSCRIPT_DIR", str(tmp_path / "edited"))
    monkeypatch.setenv("FLUENTFLOW_TRANSCRIPT_EDIT_RECORDS_DIR", str(tmp_path / "edit-records"))
    monkeypatch.setenv("FLUENTFLOW_VIDEO_SOURCE_DIR", str(tmp_path / "video-sources"))


def _status_by_name(payload: dict, name: str) -> str:
    for item in payload["checks"]:
        if item["name"] == name:
            return item["status"]
    raise AssertionError(f"missing check {name}")


def test_deployment_readiness_fails_without_public_beta_basics(monkeypatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    _isolate_machine_state(monkeypatch, tmp_path)
    _set_storage_dirs(monkeypatch, tmp_path)

    payload = run_checks()

    assert payload["status"] == "fail"
    assert _status_by_name(payload, "public_mode") == "fail"
    assert _status_by_name(payload, "access_control") == "fail"
    assert _status_by_name(payload, "azure_batch_credentials") == "fail"


def test_deployment_readiness_passes_core_cloud_configuration(monkeypatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    _isolate_machine_state(monkeypatch, tmp_path)
    _set_storage_dirs(monkeypatch, tmp_path)
    monkeypatch.setenv("FLUENTFLOW_PUBLIC_MODE", "1")
    monkeypatch.setenv("FLUENTFLOW_ACCESS_TOKEN", "beta-code")
    monkeypatch.setenv("FLUENTFLOW_ALLOWED_STT_PROVIDERS", "azure_batch")
    monkeypatch.setenv("FLUENTFLOW_DEFAULT_STT_PROVIDER", "azure_batch")
    monkeypatch.setenv("AZURE_SPEECH_ENDPOINT", "https://eastasia.api.cognitive.microsoft.com")
    monkeypatch.setenv("AZURE_SPEECH_KEY", "azure-key")
    monkeypatch.setenv("AZURE_BLOB_CONTAINER_SAS_URL", "https://example.blob.core.windows.net/audio?sig=token")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")

    payload = run_checks()

    assert payload["status"] in {"pass", "warn"}
    assert _status_by_name(payload, "public_mode") == "pass"
    assert _status_by_name(payload, "stt_provider_policy") == "pass"
    assert _status_by_name(payload, "azure_batch_credentials") == "pass"
    assert "azure-key" not in str(payload)
    assert "deepseek-key" not in str(payload)


def test_deployment_readiness_blocks_local_provider_in_public_mode(monkeypatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    _isolate_machine_state(monkeypatch, tmp_path)
    _set_storage_dirs(monkeypatch, tmp_path)
    monkeypatch.setenv("FLUENTFLOW_PUBLIC_MODE", "1")
    monkeypatch.setenv("FLUENTFLOW_ACCESS_TOKEN", "beta-code")
    monkeypatch.setenv("FLUENTFLOW_ALLOWED_STT_PROVIDERS", "local,azure_batch")
    monkeypatch.setenv("AZURE_SPEECH_ENDPOINT", "https://eastasia.api.cognitive.microsoft.com")
    monkeypatch.setenv("AZURE_SPEECH_KEY", "azure-key")
    monkeypatch.setenv("AZURE_BLOB_CONTAINER_SAS_URL", "https://example.blob.core.windows.net/audio?sig=token")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    payload = run_checks()

    assert payload["status"] == "fail"
    assert _status_by_name(payload, "stt_provider_policy") == "fail"


def test_deployment_readiness_allows_quota_guard_without_access_code(monkeypatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    _isolate_machine_state(monkeypatch, tmp_path)
    _set_storage_dirs(monkeypatch, tmp_path)
    monkeypatch.setenv("FLUENTFLOW_PUBLIC_MODE", "1")
    monkeypatch.setenv("FLUENTFLOW_ALLOWED_STT_PROVIDERS", "azure_batch")
    monkeypatch.setenv("FLUENTFLOW_DEFAULT_STT_PROVIDER", "azure_batch")
    monkeypatch.setenv("FLUENTFLOW_MAX_ACTIVE_JOBS_PER_CLIENT", "2")
    monkeypatch.setenv("FLUENTFLOW_DAILY_JOB_LIMIT_PER_CLIENT", "10")
    monkeypatch.setenv("FLUENTFLOW_DAILY_UPLOAD_MB_PER_CLIENT", "4096")
    monkeypatch.setenv("AZURE_SPEECH_ENDPOINT", "https://eastasia.api.cognitive.microsoft.com")
    monkeypatch.setenv("AZURE_SPEECH_KEY", "azure-key")
    monkeypatch.setenv("AZURE_BLOB_CONTAINER_SAS_URL", "https://example.blob.core.windows.net/audio?sig=token")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")

    payload = run_checks()

    assert payload["status"] == "warn"
    assert _status_by_name(payload, "access_control") == "warn"
    assert _status_by_name(payload, "quota_guard") == "pass"
