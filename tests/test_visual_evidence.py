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
