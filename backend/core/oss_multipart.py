"""Alibaba Cloud OSS multipart operations used by the direct-upload session API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable, Protocol

from backend.core.oss_config import OssDirectUploadConfig


class OssMultipartError(RuntimeError):
    """Raised when the server cannot complete an OSS control-plane operation."""


@dataclass(frozen=True)
class OssPartSignature:
    method: str
    url: str
    headers: dict[str, str]


class OssMultipartGateway(Protocol):
    def initiate(self, *, object_key: str, content_type: str | None) -> str: ...

    def presign_part(self, *, object_key: str, upload_id: str, part_number: int, expires_seconds: int) -> OssPartSignature: ...

    def complete(self, *, object_key: str, upload_id: str, parts: Iterable[tuple[int, str]]) -> None: ...

    def head_size(self, *, object_key: str) -> int: ...

    def abort(self, *, object_key: str, upload_id: str) -> None: ...

    def delete(self, *, object_key: str) -> None: ...


class AlibabaOssMultipartGateway:
    """OSS SDK V2 wrapper authenticated only through the ECS RAM role."""

    def __init__(self, config: OssDirectUploadConfig):
        try:
            import alibabacloud_oss_v2 as oss
            from alibabacloud_credentials.client import Client as CredentialsClient
            from alibabacloud_credentials.models import Config as CredentialsConfig
        except ImportError as exc:  # pragma: no cover - validated by deployment dependencies
            raise OssMultipartError("oss_sdk_unavailable") from exc

        credential_client = CredentialsClient(
            CredentialsConfig(type="ecs_ram_role", role_name=config.ecs_ram_role)
        )

        def credentials_provider():
            credential = credential_client.get_credential()
            return oss.credentials.Credentials(
                access_key_id=credential.access_key_id,
                access_key_secret=credential.access_key_secret,
                security_token=credential.security_token,
            )

        sdk_config = oss.config.load_default()
        sdk_config.credentials_provider = oss.credentials.CredentialsProviderFunc(func=credentials_provider)
        sdk_config.region = config.region
        sdk_config.endpoint = config.endpoint
        self._oss = oss
        self._bucket = config.bucket
        self._client = oss.Client(sdk_config)

    def initiate(self, *, object_key: str, content_type: str | None) -> str:
        result = self._client.initiate_multipart_upload(
            self._oss.InitiateMultipartUploadRequest(
                bucket=self._bucket,
                key=object_key,
                content_type=content_type or None,
            )
        )
        upload_id = str(getattr(result, "upload_id", "") or "")
        if not upload_id:
            raise OssMultipartError("oss_missing_upload_id")
        return upload_id

    def presign_part(self, *, object_key: str, upload_id: str, part_number: int, expires_seconds: int) -> OssPartSignature:
        result = self._client.presign(
            self._oss.UploadPartRequest(
                bucket=self._bucket,
                key=object_key,
                upload_id=upload_id,
                part_number=part_number,
            ),
            expires=timedelta(seconds=expires_seconds),
        )
        return OssPartSignature(
            method=str(result.method),
            url=str(result.url),
            headers={str(key): str(value) for key, value in dict(result.signed_headers or {}).items()},
        )

    def complete(self, *, object_key: str, upload_id: str, parts: Iterable[tuple[int, str]]) -> None:
        upload_parts = [self._oss.UploadPart(part_number=number, etag=etag) for number, etag in parts]
        self._client.complete_multipart_upload(
            self._oss.CompleteMultipartUploadRequest(
                bucket=self._bucket,
                key=object_key,
                upload_id=upload_id,
                complete_multipart_upload=self._oss.CompleteMultipartUpload(parts=upload_parts),
            )
        )

    def head_size(self, *, object_key: str) -> int:
        result = self._client.head_object(self._oss.HeadObjectRequest(bucket=self._bucket, key=object_key))
        return int(getattr(result, "content_length", -1) or -1)

    def abort(self, *, object_key: str, upload_id: str) -> None:
        self._client.abort_multipart_upload(
            self._oss.AbortMultipartUploadRequest(bucket=self._bucket, key=object_key, upload_id=upload_id)
        )

    def delete(self, *, object_key: str) -> None:
        self._client.delete_object(self._oss.DeleteObjectRequest(bucket=self._bucket, key=object_key))


def build_oss_multipart_gateway(config: OssDirectUploadConfig) -> OssMultipartGateway:
    return AlibabaOssMultipartGateway(config)


__all__ = ["OssMultipartError", "OssMultipartGateway", "OssPartSignature", "build_oss_multipart_gateway"]
