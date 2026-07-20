from __future__ import annotations

import json
import sqlite3
import uuid

import httpx

from backend.core import desktop_sync_client as client


def _write_connected_config(path) -> None:
    path.write_text(
        json.dumps(
            {
                "desktop_sync": {
                    "cloud_url": "https://cloud.example.test",
                    "device_id": "device-001",
                    "device_credential": "ffd_local_only_credential",
                    "display_name": "Test Mac",
                    "platform": "macos",
                }
            }
        ),
        encoding="utf-8",
    )


class _Response:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    @property
    def is_error(self) -> bool:
        return self.status_code >= 400

    def json(self) -> dict:
        return self._payload


class _CloudClient:
    def __init__(self, calls: list[tuple[str, str, dict]]) -> None:
        self.calls = calls
        self.revision = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def post(self, url: str, *, headers: dict, json: dict) -> _Response:
        self.calls.append(("post", url, json))
        return _Response(200, {"ok": True, "task": {"result_revision": self.revision}})

    def patch(self, url: str, *, headers: dict, json: dict) -> _Response:
        self.calls.append(("patch", url, json))
        assert json["base_revision"] == self.revision
        self.revision += 1
        return _Response(200, {"ok": True, "result_revision": self.revision})

    def put(self, url: str, *, headers: dict, json: dict) -> _Response:
        self.calls.append(("put", url, json))
        assert json["base_revision"] == self.revision
        self.revision += 1
        return _Response(200, {"ok": True, "result_revision": self.revision})


def test_desktop_outbox_syncs_portable_result_in_order(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.json"
    outbox_path = tmp_path / "desktop-sync.sqlite"
    _write_connected_config(config_path)
    calls: list[tuple[str, str, dict]] = []
    fake_client = _CloudClient(calls)
    monkeypatch.setattr(client.httpx, "Client", lambda **_kwargs: fake_client)
    task_id = uuid.uuid4().hex

    assert client.queue_desktop_task(
        task_id=task_id,
        source={"type": "video", "filename": "lecture.mp4", "file_size_bytes": 1024, "duration_seconds": 60},
        config_path=config_path,
        outbox_path=outbox_path,
    )
    assert client.queue_desktop_status(task_id=task_id, status="running", stage="stt", progress=30, outbox_path=outbox_path)
    assert client.queue_desktop_result(
        task_id=task_id,
        result={
            "transcript_text": "A complete transcript.",
            "raw_segments": [{"start": 0, "end": 2, "text": "A complete transcript."}],
            "display_segments": [{"start": 0, "end": 2, "text": "A complete transcript."}],
            "summary_markdown": "# Note\n![Local frame](/jobs/example/artifacts/frame.png)",
            "artifacts": {"source": {"url": "file:///Users/example/lecture.mp4"}},
            "source_path": "/Users/example/lecture.mp4",
        },
        outbox_path=outbox_path,
    )

    outcome = client.flush_desktop_sync_outbox(config_path=config_path, outbox_path=outbox_path)

    assert outcome == {"sent": 4, "pending": 0, "skipped": 0}
    assert [method for method, _url, _payload in calls] == ["post", "patch", "patch", "put"]
    assert calls[0][2]["task_id"] == task_id
    result_payload = calls[-1][2]["result"]
    assert result_payload["summary_markdown"] == "# Note\n"
    assert "artifacts" not in result_payload
    assert "source_path" not in result_payload
    assert "/Users/example" not in json.dumps(calls[-1][2])


def test_desktop_outbox_retries_same_registration_after_network_failure(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.json"
    outbox_path = tmp_path / "desktop-sync.sqlite"
    _write_connected_config(config_path)
    task_id = uuid.uuid4().hex
    assert client.queue_desktop_task(
        task_id=task_id,
        source={"type": "audio", "filename": "lesson.m4a"},
        config_path=config_path,
        outbox_path=outbox_path,
    )

    class OfflineClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def post(self, *_args, **_kwargs):
            raise httpx.ConnectError("offline")

    monkeypatch.setattr(client.httpx, "Client", lambda **_kwargs: OfflineClient())
    first = client.flush_desktop_sync_outbox(config_path=config_path, outbox_path=outbox_path)
    assert first == {"sent": 0, "pending": 2, "skipped": 0}

    with sqlite3.connect(outbox_path) as conn:
        operation_id = conn.execute(
            "SELECT operation_id FROM desktop_sync_outbox WHERE operation_kind = 'create'"
        ).fetchone()[0]
        conn.execute("UPDATE desktop_sync_outbox SET next_attempt_at = '1970-01-01T00:00:00+00:00'")

    calls: list[tuple[str, str, dict]] = []
    fake_client = _CloudClient(calls)
    monkeypatch.setattr(client.httpx, "Client", lambda **_kwargs: fake_client)
    second = client.flush_desktop_sync_outbox(config_path=config_path, outbox_path=outbox_path)

    assert second == {"sent": 2, "pending": 0, "skipped": 0}
    assert calls[0][2]["idempotency_key"] == task_id
    assert operation_id == f"create:{task_id}"
