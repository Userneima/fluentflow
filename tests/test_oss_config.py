from __future__ import annotations

from backend.core.oss_config import oss_direct_upload_config


OSS_ENV_KEYS = (
    "FLUENTFLOW_OSS_DIRECT_UPLOAD_ENABLED",
    "FLUENTFLOW_OSS_REGION",
    "FLUENTFLOW_OSS_ENDPOINT",
    "FLUENTFLOW_OSS_PUBLIC_ENDPOINT",
    "FLUENTFLOW_OSS_INTERNAL_ENDPOINT",
    "FLUENTFLOW_OSS_BUCKET",
    "FLUENTFLOW_OSS_SOURCE_PREFIX",
    "FLUENTFLOW_OSS_MULTIPART_PART_SIZE_MB",
    "FLUENTFLOW_OSS_PRESIGN_TTL_SECONDS",
    "FLUENTFLOW_OSS_UPLOAD_SESSION_TTL_SECONDS",
    "FLUENTFLOW_OSS_MAX_OPEN_SESSIONS_PER_CLIENT",
    "FLUENTFLOW_OSS_MAX_SOURCE_MB",
    "FLUENTFLOW_OSS_ECS_RAM_ROLE",
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
    assert config.upload_session_ttl_seconds == 43200
    assert config.max_open_sessions_per_client == 3
    assert config.max_source_size_mb == 4096
    assert config.ecs_ram_role == ""


def test_oss_direct_upload_accepts_complete_hong_kong_configuration(monkeypatch) -> None:
    _clear_oss_env(monkeypatch)
    monkeypatch.setenv("FLUENTFLOW_OSS_DIRECT_UPLOAD_ENABLED", "1")
    monkeypatch.setenv("FLUENTFLOW_OSS_REGION", "cn-hongkong")
    monkeypatch.setenv("FLUENTFLOW_OSS_ENDPOINT", "https://oss-cn-hongkong.aliyuncs.com/")
    monkeypatch.setenv("FLUENTFLOW_OSS_BUCKET", "fluentflow-media-test")
    monkeypatch.setenv("FLUENTFLOW_OSS_SOURCE_PREFIX", "/uploads/source")
    monkeypatch.setenv("FLUENTFLOW_OSS_MULTIPART_PART_SIZE_MB", "32")
    monkeypatch.setenv("FLUENTFLOW_OSS_PRESIGN_TTL_SECONDS", "900")
    monkeypatch.setenv("FLUENTFLOW_OSS_UPLOAD_SESSION_TTL_SECONDS", "43200")
    monkeypatch.setenv("FLUENTFLOW_OSS_MAX_OPEN_SESSIONS_PER_CLIENT", "3")
    monkeypatch.setenv("FLUENTFLOW_OSS_ECS_RAM_ROLE", "FluentFlowOssUploadRole")

    config = oss_direct_upload_config()

    assert config.ready is True
    assert config.endpoint == "oss-cn-hongkong.aliyuncs.com"
    assert config.public_endpoint == "oss-cn-hongkong.aliyuncs.com"
    assert config.internal_endpoint == "oss-cn-hongkong-internal.aliyuncs.com"
    assert config.max_source_size_mb == 4096
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
    monkeypatch.setenv("FLUENTFLOW_OSS_UPLOAD_SESSION_TTL_SECONDS", "60")
    monkeypatch.setenv("FLUENTFLOW_OSS_MAX_OPEN_SESSIONS_PER_CLIENT", "0")

    config = oss_direct_upload_config()

    assert config.ready is False
    assert len(config.errors) == 9


def test_oss_direct_upload_accepts_explicit_endpoint_pair_and_rejects_public_internal_reuse(monkeypatch) -> None:
    _clear_oss_env(monkeypatch)
    monkeypatch.setenv("FLUENTFLOW_OSS_DIRECT_UPLOAD_ENABLED", "1")
    monkeypatch.setenv("FLUENTFLOW_OSS_REGION", "cn-hongkong")
    monkeypatch.setenv("FLUENTFLOW_OSS_PUBLIC_ENDPOINT", "oss-cn-hongkong.aliyuncs.com")
    monkeypatch.setenv("FLUENTFLOW_OSS_INTERNAL_ENDPOINT", "oss-cn-hongkong-internal.aliyuncs.com")
    monkeypatch.setenv("FLUENTFLOW_OSS_BUCKET", "fluentflow-media-test")
    monkeypatch.setenv("FLUENTFLOW_OSS_ECS_RAM_ROLE", "FluentFlowOssUploadRole")
    monkeypatch.setenv("FLUENTFLOW_OSS_MAX_SOURCE_MB", "4096")

    config = oss_direct_upload_config()

    assert config.ready is True
    assert config.public_endpoint == "oss-cn-hongkong.aliyuncs.com"
    assert config.internal_endpoint == "oss-cn-hongkong-internal.aliyuncs.com"

    monkeypatch.setenv("FLUENTFLOW_OSS_INTERNAL_ENDPOINT", "oss-cn-hongkong.aliyuncs.com")
    invalid_config = oss_direct_upload_config()

    assert invalid_config.ready is False
    assert "FLUENTFLOW_OSS_INTERNAL_ENDPOINT must differ from the browser public endpoint" in invalid_config.errors


def test_oss_direct_upload_requires_an_explicit_enable_flag(monkeypatch) -> None:
    _clear_oss_env(monkeypatch)
    monkeypatch.setenv("FLUENTFLOW_OSS_REGION", "cn-hongkong")
    monkeypatch.setenv("FLUENTFLOW_OSS_PUBLIC_ENDPOINT", "oss-cn-hongkong.aliyuncs.com")
    monkeypatch.setenv("FLUENTFLOW_OSS_INTERNAL_ENDPOINT", "oss-cn-hongkong-internal.aliyuncs.com")
    monkeypatch.setenv("FLUENTFLOW_OSS_BUCKET", "fluentflow-media-test")
    monkeypatch.setenv("FLUENTFLOW_OSS_ECS_RAM_ROLE", "FluentFlowOssUploadRole")

    config = oss_direct_upload_config()

    assert config.enabled is False
    assert config.ready is False
