from __future__ import annotations

from backend.core.visual_evidence import build_visual_evidence_from_note_images, rewrite_note_image_references


def test_build_visual_evidence_from_agent_selected_note_images() -> None:
    payload = build_visual_evidence_from_note_images(
        "## 核心概念\n\n![流程图展示了 Agent 执行路线](scene_0001.jpg)\n",
        [
            {
                "kind": "frame",
                "filename": "frames/scene_0001.jpg",
                "url": "/jobs/task/artifacts/frame?file=scene_0001.jpg",
                "timestamp_seconds": 12.5,
                "provider": "local_ffmpeg",
            }
        ],
    )

    assert payload["visual_evidence_status"] == "completed"
    assert payload["visual_evidence"][0]["reason"] == "流程图展示了 Agent 执行路线"
    assert payload["visual_evidence"][0]["note_section"] == "核心概念"
    assert payload["visual_evidence"][0]["artifact_url"] == "/jobs/task/artifacts/frame?file=scene_0001.jpg"
    assert payload["visual_artifacts"]["visual_001"]["filename"] == "frames/scene_0001.jpg"


def test_candidate_frame_without_note_image_is_not_final_visual_evidence() -> None:
    payload = build_visual_evidence_from_note_images(
        "## 核心概念\n\n这里没有图片。\n",
        [{"kind": "frame", "filename": "frames/scene_0001.jpg", "url": "/jobs/task/artifacts/frame?file=scene_0001.jpg"}],
    )

    assert payload["visual_evidence_status"] == "unavailable"
    assert payload["visual_evidence"] == []
    assert payload["visual_artifacts"] == {}


def test_note_image_without_alt_text_is_not_promoted() -> None:
    payload = build_visual_evidence_from_note_images(
        "![](scene_0001.jpg)",
        [{"kind": "frame", "filename": "frames/scene_0001.jpg", "url": "/jobs/task/artifacts/frame?file=scene_0001.jpg"}],
    )

    assert payload["visual_evidence_status"] == "unavailable"


def test_rewrite_note_image_references_to_artifact_urls() -> None:
    markdown = "![流程图](scene_0001.jpg)\n\n![未知](missing.jpg)"
    rewritten = rewrite_note_image_references(
        markdown,
        [
            {
                "filename": "frames/scene_0001.jpg",
                "url": "/jobs/task/artifacts/frame?file=scene_0001.jpg",
            }
        ],
    )

    assert "![流程图](/jobs/task/artifacts/frame?file=scene_0001.jpg)" in rewritten
    assert "![未知](missing.jpg)" in rewritten


def test_build_visual_evidence_from_rewritten_artifact_url() -> None:
    payload = build_visual_evidence_from_note_images(
        "## 核心概念\n\n![流程图](/jobs/task/artifacts/frame?file=scene_0001.jpg)\n",
        [
            {
                "filename": "frames/scene_0001.jpg",
                "url": "/jobs/task/artifacts/frame?file=scene_0001.jpg",
            }
        ],
    )

    assert payload["visual_evidence_status"] == "completed"
    assert payload["visual_evidence"][0]["artifact_url"] == "/jobs/task/artifacts/frame?file=scene_0001.jpg"


def test_low_value_cover_image_is_removed_from_final_markdown() -> None:
    payload = build_visual_evidence_from_note_images(
        "## 开场\n\n![封面页展示课程标题](scene_0001.jpg)\n\n这里是正文。",
        [
            {
                "filename": "frames/scene_0001.jpg",
                "url": "/jobs/task/artifacts/frame?file=scene_0001.jpg",
                "timestamp_seconds": 1,
            }
        ],
    )

    assert payload["visual_evidence_status"] == "unavailable"
    assert payload["visual_evidence"] == []
    assert "scene_0001.jpg" not in payload["summary_markdown"]
    assert "这里是正文" in payload["summary_markdown"]


def test_duplicate_visual_hash_keeps_first_relevant_image() -> None:
    payload = build_visual_evidence_from_note_images(
        (
            "## 核心流程\n\n"
            "![流程图展示第一步](scene_0001.jpg)\n\n"
            "![流程图展示同一页重复内容](scene_0002.jpg)\n"
        ),
        [
            {
                "filename": "frames/scene_0001.jpg",
                "url": "/jobs/task/artifacts/frame?file=scene_0001.jpg",
                "timestamp_seconds": 10,
                "visual_hash": "ff00ff00ff00ff00",
            },
            {
                "filename": "frames/scene_0002.jpg",
                "url": "/jobs/task/artifacts/frame?file=scene_0002.jpg",
                "timestamp_seconds": 30,
                "visual_hash": "ff00ff00ff00ff01",
            },
        ],
    )

    assert payload["visual_evidence_status"] == "completed"
    assert len(payload["visual_evidence"]) == 1
    assert payload["visual_evidence"][0]["artifact_url"].endswith("scene_0001.jpg")
    assert "scene_0002.jpg" not in payload["summary_markdown"]


def test_visual_evidence_density_caps_short_notes() -> None:
    markdown = (
        "## 核心概念\n\n"
        "![流程图 A](scene_0001.jpg)\n\n"
        "![结构图 B](scene_0002.jpg)\n\n"
        "![代码片段 C](scene_0003.jpg)\n\n"
        "简短说明。"
    )
    payload = build_visual_evidence_from_note_images(
        markdown,
        [
            {
                "filename": f"frames/scene_{index:04d}.jpg",
                "url": f"/jobs/task/artifacts/frame?file=scene_{index:04d}.jpg",
                "timestamp_seconds": index * 10,
                "visual_hash": visual_hash,
            }
            for index, visual_hash in enumerate(
                ["0000000000000000", "ffffffffffffffff", "00ff00ff00ff00ff"],
                start=1,
            )
        ],
    )

    assert len(payload["visual_evidence"]) == 2
    assert "scene_0003.jpg" not in payload["summary_markdown"]
