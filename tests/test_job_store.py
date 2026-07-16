from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from backend.core.job_store import (
    acquire_next_job_step,
    cancel_job_steps,
    complete_job_step,
    delete_jobs,
    enqueue_job_step,
    ensure_job_db,
    fail_job_step,
    get_job,
    heartbeat_job_step,
    list_job_steps,
    list_jobs,
    list_jobs_for_retention,
    migrate_job_display_titles,
    requeue_running_job_steps,
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


def test_upsert_job_merges_metadata_instead_of_replacing_it(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"

    upsert_job(
        task_id="guest-task",
        status="queued",
        metadata={
            "route": "/guest-trial/process",
            "queue_options": {"ai_provider": "qwen"},
            "guest_trial": {"token": "guest-token"},
        },
        db_path=db,
    )
    upsert_job(
        task_id="guest-task",
        status="running",
        stage="stt",
        metadata={
            "route": "/process",
            "stt_provider": "elevenlabs_scribe",
        },
        db_path=db,
    )

    job = get_job("guest-task", db_path=db)
    assert job is not None
    assert job["metadata"]["route"] == "/process"
    assert job["metadata"]["stt_provider"] == "elevenlabs_scribe"
    assert job["metadata"]["queue_options"] == {"ai_provider": "qwen"}
    assert job["metadata"]["guest_trial"] == {"token": "guest-token"}


def test_job_store_writes_current_result_schema_without_legacy_segment_aliases(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"

    upsert_job(
        task_id="task-schema",
        status="completed",
        result={
            "task_id": "task-schema",
            "transcript_text": "Hello",
            "segments": [{"start": 0, "end": 1, "text": "Hello"}],
            "translated_segments_zh": [{"start": 0, "end": 1, "text": "你好"}],
        },
        db_path=db,
    )

    job = get_job("task-schema", db_path=db)
    with sqlite3.connect(db) as conn:
        raw = conn.execute("SELECT result_json FROM jobs WHERE task_id = ?", ("task-schema",)).fetchone()[0]
    stored = json.loads(raw)

    assert job is not None
    assert stored["result_schema_version"] == "2"
    assert stored["raw_segments"][0]["text"] == "Hello"
    assert stored["display_segments"][0]["text_zh"] == "你好"
    assert "segments" not in stored
    assert "bilingual_segments" not in stored
    assert "translated_segments_zh" not in stored
    assert "cleaned_segments" not in stored
    assert job["result"] == stored


def test_job_store_reads_legacy_result_as_current_schema_without_rewriting_db(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"
    ensure_job_db(db)
    legacy_result = {
        "task_id": "task-legacy-schema",
        "transcript_text": "Hello",
        "segments": [{"start": 0, "end": 1, "text": "Hello"}],
        "translated_segments_zh": [{"start": 0, "end": 1, "text": "你好"}],
    }
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                task_id, created_at, updated_at, status, result_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("task-legacy-schema", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", "completed", json.dumps(legacy_result)),
        )

    job = get_job("task-legacy-schema", db_path=db)
    with sqlite3.connect(db) as conn:
        raw = conn.execute("SELECT result_json FROM jobs WHERE task_id = ?", ("task-legacy-schema",)).fetchone()[0]

    assert job is not None
    assert job["result"]["result_schema_version"] == "2"
    assert job["result"]["result_schema_migrated_from"] == "legacy"
    assert job["result"]["raw_segments"][0]["text"] == "Hello"
    assert job["result"]["display_segments"][0]["text_zh"] == "你好"
    assert "segments" not in job["result"]
    assert json.loads(raw) == legacy_result


def test_job_steps_are_persistent_claimable_and_completable(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"

    step = enqueue_job_step(
        task_id="task-step",
        step_type="transcription",
        input={"source_path": "/tmp/source.mp4"},
        db_path=db,
    )
    claimed = acquire_next_job_step(db_path=db)

    assert step is not None
    assert claimed is not None
    assert claimed["task_id"] == "task-step"
    assert claimed["step_type"] == "transcription"
    assert claimed["status"] == "running"
    assert claimed["attempt_count"] == 1
    assert claimed["input"]["source_path"] == "/tmp/source.mp4"

    completed = complete_job_step(
        claimed["id"], lock_id=claimed["lock_id"], result={"ok": True}, db_path=db
    )

    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["result"] == {"ok": True}
    assert acquire_next_job_step(db_path=db) is None


def test_queued_steps_are_handed_out_one_at_a_time_in_order(tmp_path: Path) -> None:
    # Guards the multi-file queue invariant: several files enqueued at once must
    # be processed serially, in FIFO order, and a step already claimed (running,
    # not yet finished) must never be handed to a second worker. Regression origin:
    # multiple videos could not be queued into notes (2026-07-08).
    db = tmp_path / "jobs.sqlite"

    first = enqueue_job_step(
        task_id="task-a", step_type="transcription", input={"n": 1}, db_path=db
    )
    second = enqueue_job_step(
        task_id="task-b", step_type="transcription", input={"n": 2}, db_path=db
    )
    assert first is not None and second is not None

    claimed_a = acquire_next_job_step(db_path=db)
    assert claimed_a is not None
    assert claimed_a["task_id"] == "task-a"  # FIFO: earliest enqueued goes first

    # The first step is now running/locked. A second acquire must NOT re-hand it;
    # it must hand out the next queued step instead — this is what keeps
    # processing to one file at a time without double-claiming.
    claimed_b = acquire_next_job_step(db_path=db)
    assert claimed_b is not None
    assert claimed_b["task_id"] == "task-b"
    assert claimed_a["id"] != claimed_b["id"]

    # With both steps claimed and none completed, there is nothing left to hand out.
    assert acquire_next_job_step(db_path=db) is None

    # Both finish independently; the queue drains completely.
    assert complete_job_step(
        claimed_a["id"], lock_id=claimed_a["lock_id"], result={"ok": True}, db_path=db
    ) is not None
    assert complete_job_step(
        claimed_b["id"], lock_id=claimed_b["lock_id"], result={"ok": True}, db_path=db
    ) is not None
    assert acquire_next_job_step(db_path=db) is None


def test_running_job_steps_requeue_and_cancel_by_task(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"
    enqueue_job_step(task_id="task-recover", step_type="transcription", input={}, db_path=db)
    claimed = acquire_next_job_step(db_path=db)

    assert claimed is not None
    assert requeue_running_job_steps(db_path=db) == 1
    assert list_job_steps(task_id="task-recover", statuses=["queued"], db_path=db)
    assert cancel_job_steps("task-recover", db_path=db) == 1
    assert list_job_steps(task_id="task-recover", statuses=["cancelled"], db_path=db)


def test_step_lease_heartbeat_and_owner_token_prevent_stale_worker_writes(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"
    enqueue_job_step(task_id="task-lease", step_type="transcription", input={}, db_path=db)
    first_claim = acquire_next_job_step(db_path=db)

    assert first_claim is not None
    assert heartbeat_job_step(first_claim["id"], lock_id=first_claim["lock_id"], db_path=db) is True

    # Simulate a worker that stopped heartbeating. A new claimant may recover the
    # expired lease, but the old owner must not be able to complete it afterwards.
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE job_steps SET locked_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", first_claim["id"]),
        )
    recovered_claim = acquire_next_job_step(lock_timeout_seconds=60, db_path=db)

    assert recovered_claim is not None
    assert recovered_claim["id"] == first_claim["id"]
    assert recovered_claim["lock_id"] != first_claim["lock_id"]
    assert complete_job_step(
        first_claim["id"], lock_id=first_claim["lock_id"], result={"old": True}, db_path=db
    ) is None
    assert fail_job_step(
        first_claim["id"], lock_id=first_claim["lock_id"], error_reason="old worker", db_path=db
    ) is None

    completed = complete_job_step(
        recovered_claim["id"], lock_id=recovered_claim["lock_id"], result={"recovered": True}, db_path=db
    )
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["result"] == {"recovered": True}


def test_reenqueue_does_not_clear_an_active_step_lease(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"
    enqueue_job_step(task_id="task-active", step_type="transcription", input={"version": 1}, db_path=db)
    claimed = acquire_next_job_step(db_path=db)

    assert claimed is not None
    enqueue_job_step(task_id="task-active", step_type="transcription", input={"version": 2}, db_path=db)
    active = list_job_steps(task_id="task-active", statuses=["running"], db_path=db)

    assert active[0]["lock_id"] == claimed["lock_id"]
    assert active[0]["input"] == {"version": 1}


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


def test_migrate_job_display_titles_cleans_existing_bilibili_display_title(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"

    upsert_job(
        task_id="task-bili",
        status="completed",
        source_type="video",
        source_filename="BV1JBoEBbEH7-5步用AI从零打造IP吉祥物全案.mp4",
        result={
            "task_id": "task-bili",
            "filename": "BV1JBoEBbEH7-5步用AI从零打造IP吉祥物全案.mp4",
            "raw_title": "BV1JBoEBbEH7-5步用AI从零打造IP吉祥物全案",
            "display_title": "BV1JBoEBbEH7-5步用AI从零打造IP吉祥物全案",
            "transcript_text": "text",
        },
        metadata={
            "route": "/video-sources/jobs",
            "raw_title": "BV1JBoEBbEH7-5步用AI从零打造IP吉祥物全案",
            "display_title": "BV1JBoEBbEH7-5步用AI从零打造IP吉祥物全案",
            "video_source": {
                "raw_title": "BV1JBoEBbEH7-5步用AI从零打造IP吉祥物全案",
                "display_title": "BV1JBoEBbEH7-5步用AI从零打造IP吉祥物全案",
            },
        },
        db_path=db,
    )

    assert migrate_job_display_titles(db_path=db) == 1
    job = get_job("task-bili", db_path=db)

    assert job is not None
    assert job["metadata"]["display_title"] == "5步用AI从零打造IP吉祥物全案"
    assert job["metadata"]["video_source"]["display_title"] == "5步用AI从零打造IP吉祥物全案"
    assert job["result"]["display_title"] == "5步用AI从零打造IP吉祥物全案"


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
