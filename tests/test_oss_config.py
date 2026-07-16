from __future__ import annotations

from backend.core.oss_config import oss_direct_upload_config


OSS_ENV_KEYS = (
    "FLUENTFLOW_OSS_DIRECT_UPLOAD_ENABLED",
    "FLUENTFLOW_OSS_REGION",
    "FLUENTFLOW_OSS_ENDPOINT",
    "FLUENTFLOW_OSS_BUCKET",
    "FLUENTFLOW_OSS_SOURCE_PREFIX",
    "FLUENTFLOW_OSS_MULTIPART_PART_SIZE_MB",
    "FLUENTFLOW_OSS_PRESIGN_TTL_SECONDS",
)


def _clear_oss_env(monkeypatch) -> None:
    for key in OSS_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_oss_direct_upload_stays_disabled_by_default(monkeypatch) -> None:
    _clear_oss_env(monkeypatch)

    config = oss_direct_upload_config()

    assert config.enabled is False
    assert config.ready is False
    assert config.errors == ()
    assert config.source_prefix == "uploads/source/"
    assert config.multipart_part_size_mb == 32
    assert config.presign_ttl_seconds == 900


def test_oss_direct_upload_accepts_complete_hong_kong_configuration(monkeypatch) -> None:
    _clear_oss_env(monkeypatch)
    monkeypatch.setenv("FLUENTFLOW_OSS_DIRECT_UPLOAD_ENABLED", "1")
    monkeypatch.setenv("FLUENTFLOW_OSS_REGION", "cn-hongkong")
    monkeypatch.setenv("FLUENTFLOW_OSS_ENDPOINT", "https://oss-cn-hongkong.aliyuncs.com/")
    monkeypatch.setenv("FLUENTFLOW_OSS_BUCKET", "fluentflow-media-test")
    monkeypatch.setenv("FLUENTFLOW_OSS_SOURCE_PREFIX", "/uploads/source")
    monkeypatch.setenv("FLUENTFLOW_OSS_MULTIPART_PART_SIZE_MB", "32")
    monkeypatch.setenv("FLUENTFLOW_OSS_PRESIGN_TTL_SECONDS", "900")

    config = oss_direct_upload_config()

    assert config.ready is True
    assert config.endpoint == "oss-cn-hongkong.aliyuncs.com"
    assert config.source_prefix == "uploads/source/"
    assert config.errors == ()


def test_oss_direct_upload_reports_missing_or_unsafe_settings(monkeypatch) -> None:
    _clear_oss_env(monkeypatch)
    monkeypatch.setenv("FLUENTFLOW_OSS_DIRECT_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("FLUENTFLOW_OSS_REGION", "us-example")
    monkeypatch.setenv("FLUENTFLOW_OSS_ENDPOINT", "https://oss.example.com/upload")
    monkeypatch.setenv("FLUENTFLOW_OSS_BUCKET", "Bad Bucket")
    monkeypatch.setenv("FLUENTFLOW_OSS_SOURCE_PREFIX", "../uploads")
    monkeypatch.setenv("FLUENTFLOW_OSS_MULTIPART_PART_SIZE_MB", "1")
    monkeypatch.setenv("FLUENTFLOW_OSS_PRESIGN_TTL_SECONDS", "10")

    config = oss_direct_upload_config()

    assert config.ready is False
    assert len(config.errors) == 6
