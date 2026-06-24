from __future__ import annotations

from pathlib import Path
import sqlite3

from backend.core.job_store import (
    delete_jobs,
    ensure_job_db,
    get_job,
    list_jobs,
    list_jobs_for_retention,
    migrate_job_display_titles,
    update_job_result,
    upsert_job,
)


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


def test_migrate_job_display_titles_backfills_legacy_video_jobs(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"

    upsert_job(
        task_id="task-legacy",
        status="completed",
        source_type="video",
        source_filename="7651613998131006774-四大核心Skill架构与配置指南详解.mp4",
        result={
            "task_id": "task-legacy",
            "filename": "7651613998131006774-四大核心Skill架构与配置指南详解.mp4",
            "transcript_text": "text",
        },
        metadata={
            "route": "/video-sources/jobs",
            "video_source": {
                "title": "7651613998131006774-四大核心Skill架构与配置指南详解",
                "filename": "7651613998131006774-四大核心Skill架构与配置指南详解.mp4",
            },
        },
        db_path=db,
    )
    before = get_job("task-legacy", db_path=db)

    assert migrate_job_display_titles(db_path=db) == 1
    job = get_job("task-legacy", db_path=db)

    assert job is not None
    assert before is not None
    assert job["updated_at"] == before["updated_at"]
    assert job["source_filename"] == "7651613998131006774-四大核心Skill架构与配置指南详解.mp4"
    assert job["metadata"]["raw_title"] == "7651613998131006774-四大核心Skill架构与配置指南详解"
    assert job["metadata"]["display_title"] == "四大核心Skill架构与配置指南详解"
    assert job["metadata"]["video_source"]["display_title"] == "四大核心Skill架构与配置指南详解"
    assert job["result"]["raw_title"] == "7651613998131006774-四大核心Skill架构与配置指南详解"
    assert job["result"]["display_title"] == "四大核心Skill架构与配置指南详解"


def test_migrate_job_display_titles_does_not_rewrite_existing_clean_title(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"

    upsert_job(
        task_id="task-clean",
        status="completed",
        source_filename="demo.mp4",
        result={"task_id": "task-clean", "filename": "demo.mp4", "raw_title": "干净标题", "display_title": "干净标题"},
        metadata={"display_title": "干净标题", "raw_title": "干净标题"},
        db_path=db,
    )

    assert migrate_job_display_titles(db_path=db) == 0


def test_cancelled_job_cannot_be_revived_by_late_progress_update(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"

    upsert_job(
        task_id="task-cancelled",
        status="running",
        stage="stt",
        progress=40,
        source_filename="demo.mp4",
        db_path=db,
    )
    upsert_job(
        task_id="task-cancelled",
        status="cancelled",
        stage="stt",
        progress=40,
        error_reason="user_cancelled",
        db_path=db,
    )
    upsert_job(
        task_id="task-cancelled",
        status="running",
        stage="summary",
        progress=90,
        error_reason=None,
        db_path=db,
    )

    job = get_job("task-cancelled", db_path=db)
    assert job is not None
    assert job["status"] == "cancelled"
    assert job["stage"] == "stt"
    assert job["progress"] == 40
    assert job["error_reason"] == "user_cancelled"


def test_job_store_filters_by_client_id(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"

    upsert_job(
        task_id="client-a-task",
        status="completed",
        client_id="client-a",
        result={"task_id": "client-a-task"},
        db_path=db,
    )
    upsert_job(
        task_id="client-b-task",
        status="completed",
        client_id="client-b",
        result={"task_id": "client-b-task"},
        db_path=db,
    )

    assert [job["task_id"] for job in list_jobs(db_path=db, client_id="client-a")] == ["client-a-task"]
    assert get_job("client-b-task", db_path=db, client_id="client-a") is None

    updated = update_job_result(
        "client-b-task",
        {"task_id": "client-b-task", "transcript_text": "blocked"},
        db_path=db,
        client_id="client-a",
    )
    assert updated is None


def test_job_store_lists_all_jobs_for_retention_and_deletes_by_client(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"

    for idx in range(3):
        upsert_job(
            task_id=f"task-{idx}",
            status="completed",
            client_id="client-a",
            result={"task_id": f"task-{idx}"},
            db_path=db,
        )
    upsert_job(
        task_id="other-client",
        status="completed",
        client_id="client-b",
        result={"task_id": "other-client"},
        db_path=db,
    )

    assert len(list_jobs_for_retention(db_path=db, client_id="client-a")) == 3
    assert delete_jobs(["task-0", "other-client"], db_path=db, client_id="client-a") == 1
    assert get_job("task-0", db_path=db) is None
    assert get_job("other-client", db_path=db) is not None


def test_job_store_migrates_legacy_db_without_client_id(tmp_path: Path) -> None:
    db = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE jobs (
                task_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT,
                progress REAL,
                source_type TEXT,
                source_filename TEXT,
                source_file_size_mb REAL,
                summary_status TEXT,
                error_reason TEXT,
                result_json TEXT,
                metadata_json TEXT
            )
            """
        )

    ensure_job_db(db)

    with sqlite3.connect(db) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    assert "client_id" in columns
