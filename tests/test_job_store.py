from __future__ import annotations

from pathlib import Path

from backend.core.job_store import get_job, list_jobs, update_job_result, upsert_job


def test_job_store_persists_status_and_result(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"

    upsert_job(
        task_id="task-1",
        status="running",
        stage="stt",
        progress=25,
        source_type="audio",
        source_filename="demo.mp3",
        db_path=db,
    )
    upsert_job(
        task_id="task-1",
        status="completed",
        stage="done",
        progress=100,
        summary_status="completed",
        result={"task_id": "task-1", "status": "completed", "summary_markdown": "# Note"},
        db_path=db,
    )

    job = get_job("task-1", db_path=db)
    assert job is not None
    assert job["status"] == "completed"
    assert job["source_filename"] == "demo.mp3"
    assert job["result"]["summary_markdown"] == "# Note"
    assert list_jobs(db_path=db)[0]["task_id"] == "task-1"


def test_update_job_result_preserves_job_metadata(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"

    upsert_job(
        task_id="task-2",
        status="completed",
        stage="done",
        progress=100,
        source_type="audio",
        source_filename="demo.m4a",
        result={"task_id": "task-2", "transcript_text": "old"},
        db_path=db,
    )

    updated = update_job_result(
        "task-2",
        {"task_id": "task-2", "transcript_text": "new", "transcript_edited": True},
        db_path=db,
    )

    assert updated is not None
    assert updated["status"] == "completed"
    assert updated["source_filename"] == "demo.m4a"
    assert updated["result"]["transcript_text"] == "new"
    assert updated["result"]["transcript_edited"] is True
