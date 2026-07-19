"""Configuration boundary for the future direct-to-OSS multipart flow.

This module deliberately does not create an OSS client or alter any upload
route. The existing application-server upload path remains active until a
later work unit adds the authenticated upload-session API and browser client.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from backend.core._env import _env_truthy


_BUCKET_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61})[a-z0-9]$")
_RAM_ROLE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,63}$")
_MIN_MULTIPART_PART_SIZE_MB = 5
_MAX_MULTIPART_PART_SIZE_MB = 5 * 1024
_MIN_PRESIGN_TTL_SECONDS = 60
_MAX_PRESIGN_TTL_SECONDS = 60 * 60
_MIN_UPLOAD_SESSION_TTL_SECONDS = 10 * 60
_MAX_UPLOAD_SESSION_TTL_SECONDS = 24 * 60 * 60
_MIN_OPEN_SESSIONS_PER_CLIENT = 1
_MAX_OPEN_SESSIONS_PER_CLIENT = 10
_MIN_DIRECT_SOURCE_SIZE_MB = 1
_MAX_DIRECT_SOURCE_SIZE_MB = 50 * 1024


@dataclass(frozen=True)
class OssDirectUploadConfig:
    """Validated, non-secret settings for a future direct OSS upload flow."""

    enabled: bool
    region: str
    public_endpoint: str
    internal_endpoint: str
    bucket: str
    source_prefix: str
    multipart_part_size_mb: int
    presign_ttl_seconds: int
    upload_session_ttl_seconds: int
    max_open_sessions_per_client: int
    max_source_size_mb: int
    ecs_ram_role: str
    errors: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.enabled and not self.errors

    @property
    def endpoint(self) -> str:
        """Compatibility alias for callers that formerly used one endpoint."""

        return self.public_endpoint


def _integer_env(name: str, default: int) -> int:
    try:
        return int((os.environ.get(name) or str(default)).strip())
    except ValueError:
        return default


def _normalise_endpoint(value: str) -> str:
    endpoint = value.strip().lower().removeprefix("https://").removeprefix("http://").rstrip("/")
    return endpoint


def _normalise_prefix(value: str) -> str:
    prefix = value.strip().lstrip("/")
    return prefix if not prefix or prefix.endswith("/") else f"{prefix}/"


def oss_direct_upload_config() -> OssDirectUploadConfig:
    """Read direct-upload settings without enabling the upload path by default."""

    enabled = _env_truthy("FLUENTFLOW_OSS_DIRECT_UPLOAD_ENABLED")
    region = (os.environ.get("FLUENTFLOW_OSS_REGION") or "").strip().lower()
    public_endpoint = _normalise_endpoint(
        os.environ.get("FLUENTFLOW_OSS_PUBLIC_ENDPOINT") or os.environ.get("FLUENTFLOW_OSS_ENDPOINT") or ""
    )
    derived_internal_endpoint = f"oss-{region}-internal.aliyuncs.com" if region else ""
    internal_endpoint = _normalise_endpoint(
        os.environ.get("FLUENTFLOW_OSS_INTERNAL_ENDPOINT") or derived_internal_endpoint
    )
    bucket = (os.environ.get("FLUENTFLOW_OSS_BUCKET") or "").strip().lower()
    source_prefix = _normalise_prefix(os.environ.get("FLUENTFLOW_OSS_SOURCE_PREFIX") or "uploads/source/")
    multipart_part_size_mb = _integer_env("FLUENTFLOW_OSS_MULTIPART_PART_SIZE_MB", 32)
    presign_ttl_seconds = _integer_env("FLUENTFLOW_OSS_PRESIGN_TTL_SECONDS", 900)
    upload_session_ttl_seconds = _integer_env("FLUENTFLOW_OSS_UPLOAD_SESSION_TTL_SECONDS", 12 * 60 * 60)
    max_open_sessions_per_client = _integer_env("FLUENTFLOW_OSS_MAX_OPEN_SESSIONS_PER_CLIENT", 3)
    max_source_size_mb = _integer_env("FLUENTFLOW_OSS_MAX_SOURCE_MB", 4096)
    ecs_ram_role = (os.environ.get("FLUENTFLOW_OSS_ECS_RAM_ROLE") or "").strip()

    if not enabled:
        return OssDirectUploadConfig(
            enabled=False,
            region=region,
            public_endpoint=public_endpoint,
            internal_endpoint=internal_endpoint,
            bucket=bucket,
            source_prefix=source_prefix,
            multipart_part_size_mb=multipart_part_size_mb,
            presign_ttl_seconds=presign_ttl_seconds,
            upload_session_ttl_seconds=upload_session_ttl_seconds,
            max_open_sessions_per_client=max_open_sessions_per_client,
            max_source_size_mb=max_source_size_mb,
            ecs_ram_role=ecs_ram_role,
        )

    errors: list[str] = []
    if not region.startswith("cn-"):
        errors.append("FLUENTFLOW_OSS_REGION must be an Alibaba Cloud region such as cn-hongkong")
    if not public_endpoint or "/" in public_endpoint or ":" in public_endpoint:
        errors.append("FLUENTFLOW_OSS_PUBLIC_ENDPOINT must be a hostname without a protocol or path")
    if not internal_endpoint or "/" in internal_endpoint or ":" in internal_endpoint:
        errors.append("FLUENTFLOW_OSS_INTERNAL_ENDPOINT must be a hostname without a protocol or path")
    elif internal_endpoint == public_endpoint:
        errors.append("FLUENTFLOW_OSS_INTERNAL_ENDPOINT must differ from the browser public endpoint")
    if not _BUCKET_NAME.fullmatch(bucket):
        errors.append("FLUENTFLOW_OSS_BUCKET must be a valid OSS bucket name")
    if not _RAM_ROLE_NAME.fullmatch(ecs_ram_role):
        errors.append("FLUENTFLOW_OSS_ECS_RAM_ROLE must name the attached ECS RAM role")
    if not source_prefix or ".." in source_prefix.split("/"):
        errors.append("FLUENTFLOW_OSS_SOURCE_PREFIX must be a non-empty relative object prefix")
    if not _MIN_MULTIPART_PART_SIZE_MB <= multipart_part_size_mb <= _MAX_MULTIPART_PART_SIZE_MB:
        errors.append(
            "FLUENTFLOW_OSS_MULTIPART_PART_SIZE_MB must be between "
            f"{_MIN_MULTIPART_PART_SIZE_MB} and {_MAX_MULTIPART_PART_SIZE_MB}"
        )
    if not _MIN_PRESIGN_TTL_SECONDS <= presign_ttl_seconds <= _MAX_PRESIGN_TTL_SECONDS:
        errors.append(
            "FLUENTFLOW_OSS_PRESIGN_TTL_SECONDS must be between "
            f"{_MIN_PRESIGN_TTL_SECONDS} and {_MAX_PRESIGN_TTL_SECONDS}"
        )
    if not _MIN_UPLOAD_SESSION_TTL_SECONDS <= upload_session_ttl_seconds <= _MAX_UPLOAD_SESSION_TTL_SECONDS:
        errors.append(
            "FLUENTFLOW_OSS_UPLOAD_SESSION_TTL_SECONDS must be between "
            f"{_MIN_UPLOAD_SESSION_TTL_SECONDS} and {_MAX_UPLOAD_SESSION_TTL_SECONDS}"
        )
    if not _MIN_OPEN_SESSIONS_PER_CLIENT <= max_open_sessions_per_client <= _MAX_OPEN_SESSIONS_PER_CLIENT:
        errors.append(
            "FLUENTFLOW_OSS_MAX_OPEN_SESSIONS_PER_CLIENT must be between "
            f"{_MIN_OPEN_SESSIONS_PER_CLIENT} and {_MAX_OPEN_SESSIONS_PER_CLIENT}"
        )
    if not _MIN_DIRECT_SOURCE_SIZE_MB <= max_source_size_mb <= _MAX_DIRECT_SOURCE_SIZE_MB:
        errors.append(
            "FLUENTFLOW_OSS_MAX_SOURCE_MB must be between "
            f"{_MIN_DIRECT_SOURCE_SIZE_MB} and {_MAX_DIRECT_SOURCE_SIZE_MB}"
        )

    return OssDirectUploadConfig(
        enabled=True,
        region=region,
        public_endpoint=public_endpoint,
        internal_endpoint=internal_endpoint,
        bucket=bucket,
        source_prefix=source_prefix,
        multipart_part_size_mb=multipart_part_size_mb,
        presign_ttl_seconds=presign_ttl_seconds,
        upload_session_ttl_seconds=upload_session_ttl_seconds,
        max_open_sessions_per_client=max_open_sessions_per_client,
        max_source_size_mb=max_source_size_mb,
        ecs_ram_role=ecs_ram_role,
        errors=tuple(errors),
    )


__all__ = ["OssDirectUploadConfig", "oss_direct_upload_config"]
