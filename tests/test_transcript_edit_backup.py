from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import backend.main as main
import backend.core.server_helpers as _H


def test_edited_transcript_backup_overwrites_timestamped_text(tmp_path: Path) -> None:
    result = {
        "filename": "课程/录音?.m4a",
        "transcript_text": "第一版",
        "segments": [
            {"start": 0, "end": 2, "text": "第一句"},
            {"start": 62, "end": 65, "text": "第二句"},
        ],
    }

    with patch.dict("os.environ", {"FLUENTFLOW_EDITED_TRANSCRIPT_DIR": str(tmp_path)}):
        saved = _H._write_edited_transcript_backup("task-abc123", result)
        result["segments"][0]["text"] = "第一句已修改"
        _H._write_edited_transcript_backup("task-abc123", result)

    assert saved.parent == tmp_path
    assert saved.name == "录音__task-abc123_edited.txt"
    assert saved.read_text(encoding="utf-8") == "[00:00] 第一句已修改\n[01:02] 第二句\n"


def test_update_transcript_returns_backup_path(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_get_job(task_id: str, **_: object) -> dict[str, object]:
        return {
            "task_id": task_id,
            "status": "completed",
            "result": {"task_id": task_id, "filename": "demo.m4a"},
        }

    def fake_update_job_result(task_id: str, result: dict[str, object], **_: object) -> dict[str, object]:
        captured["result"] = result
        return {
            "task_id": task_id,
            "status": "completed",
            "result": result,
        }

    monkeypatch.setattr(_H, "get_job", fake_get_job)
    monkeypatch.setattr(_H, "update_job_result", fake_update_job_result)
    monkeypatch.setattr(_H, "_edited_transcript_dir", lambda: tmp_path)
    monkeypatch.setattr(_H, "_transcript_edit_records_dir", lambda: tmp_path)

    response = TestClient(main.app).patch(
        "/jobs/task-route/transcript",
        json={
            "transcript_text": "修改后的文字",
            "segments": [{"start": 3, "end": 4, "text": "修改后的文字"}],
            "edit_records": [
                {
                    "index": 0,
                    "start": 3,
                    "end": 4,
                    "before": "原始文字",
                    "after": "修改后的文字",
                    "previous_before": "上一句",
                    "next_before": "下一句",
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()
    backup_path = Path(data["result"]["edited_transcript_path"])
    records_path = Path(data["result"]["transcript_edit_records_path"])
    assert backup_path.exists()
    assert records_path.exists()
    assert backup_path.read_text(encoding="utf-8") == "[00:03] 修改后的文字\n"
    assert '"previous_before": "上一句"' in records_path.read_text(encoding="utf-8")
    assert data["result"]["transcript_edit_record_count"] == 1
    assert captured["result"]["edited_transcript_saved_at"] == data["result"]["transcript_edited_at"]
