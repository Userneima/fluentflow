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
_MIN_MULTIPART_PART_SIZE_MB = 5
_MAX_MULTIPART_PART_SIZE_MB = 5 * 1024
_MIN_PRESIGN_TTL_SECONDS = 60
_MAX_PRESIGN_TTL_SECONDS = 60 * 60


@dataclass(frozen=True)
class OssDirectUploadConfig:
    """Validated, non-secret settings for a future direct OSS upload flow."""

    enabled: bool
    region: str
    endpoint: str
    bucket: str
    source_prefix: str
    multipart_part_size_mb: int
    presign_ttl_seconds: int
    errors: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.enabled and not self.errors


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
    endpoint = _normalise_endpoint(os.environ.get("FLUENTFLOW_OSS_ENDPOINT") or "")
    bucket = (os.environ.get("FLUENTFLOW_OSS_BUCKET") or "").strip().lower()
    source_prefix = _normalise_prefix(os.environ.get("FLUENTFLOW_OSS_SOURCE_PREFIX") or "uploads/source/")
    multipart_part_size_mb = _integer_env("FLUENTFLOW_OSS_MULTIPART_PART_SIZE_MB", 32)
    presign_ttl_seconds = _integer_env("FLUENTFLOW_OSS_PRESIGN_TTL_SECONDS", 900)

    if not enabled:
        return OssDirectUploadConfig(
            enabled=False,
            region=region,
            endpoint=endpoint,
            bucket=bucket,
            source_prefix=source_prefix,
            multipart_part_size_mb=multipart_part_size_mb,
            presign_ttl_seconds=presign_ttl_seconds,
        )

    errors: list[str] = []
    if not region.startswith("cn-"):
        errors.append("FLUENTFLOW_OSS_REGION must be an Alibaba Cloud region such as cn-hongkong")
    if not endpoint or "/" in endpoint or ":" in endpoint:
        errors.append("FLUENTFLOW_OSS_ENDPOINT must be a hostname without a protocol or path")
    if not _BUCKET_NAME.fullmatch(bucket):
        errors.append("FLUENTFLOW_OSS_BUCKET must be a valid OSS bucket name")
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

    return OssDirectUploadConfig(
        enabled=True,
        region=region,
        endpoint=endpoint,
        bucket=bucket,
        source_prefix=source_prefix,
        multipart_part_size_mb=multipart_part_size_mb,
        presign_ttl_seconds=presign_ttl_seconds,
        errors=tuple(errors),
    )


__all__ = ["OssDirectUploadConfig", "oss_direct_upload_config"]
