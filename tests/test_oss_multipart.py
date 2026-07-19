from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from backend.core.oss_multipart import AlibabaOssMultipartGateway


class _Request:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeOss:
    InitiateMultipartUploadRequest = _Request
    UploadPartRequest = _Request
    HeadObjectRequest = _Request
    GetObjectRequest = _Request


class _FakeClient:
    def __init__(self, name: str):
        self.name = name
        self.calls: list[str] = []

    def initiate_multipart_upload(self, request):
        self.calls.append("initiate")
        return SimpleNamespace(upload_id="upload-id")

    def presign(self, request, *, expires):
        self.calls.append("presign")
        return SimpleNamespace(
            method="PUT",
            url="https://oss-cn-hongkong.aliyuncs.com/signed-part",
            signed_headers={"x-oss-security-token": "temporary"},
        )

    def head_object(self, request):
        self.calls.append("head")
        return SimpleNamespace(content_length=3)

    def get_object(self, request):
        self.calls.append("get")
        return SimpleNamespace(body=BytesIO(b"oss"))


def _gateway_with_split_clients() -> tuple[AlibabaOssMultipartGateway, _FakeClient, _FakeClient]:
    gateway = object.__new__(AlibabaOssMultipartGateway)
    public_client = _FakeClient("public")
    internal_client = _FakeClient("internal")
    gateway._oss = _FakeOss()
    gateway._bucket = "fluentflow-media-test"
    gateway._public_client = public_client
    gateway._internal_client = internal_client
    return gateway, public_client, internal_client


def test_browser_part_signing_uses_public_client_and_server_download_uses_internal_client(tmp_path) -> None:
    gateway, public_client, internal_client = _gateway_with_split_clients()

    upload_id = gateway.initiate(object_key="uploads/source/one/source.mp4", content_type="video/mp4")
    signature = gateway.presign_part(
        object_key="uploads/source/one/source.mp4",
        upload_id=upload_id,
        part_number=1,
        expires_seconds=900,
    )
    assert gateway.head_size(object_key="uploads/source/one/source.mp4") == 3
    target_path = tmp_path / "source.mp4"
    assert gateway.download_to_file(object_key="uploads/source/one/source.mp4", target_path=target_path) == 3

    assert signature.url == "https://oss-cn-hongkong.aliyuncs.com/signed-part"
    assert target_path.read_bytes() == b"oss"
    assert public_client.calls == ["presign"]
    assert internal_client.calls == ["initiate", "head", "get"]
