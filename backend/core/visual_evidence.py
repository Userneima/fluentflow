"""Build final visual evidence from Agent-selected note image references."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _plain_markdown(value: str) -> str:
    text = re.sub(r"[*_`>#]+", "", value or "")
    return re.sub(r"\s+", " ", text).strip()


def _heading_before(markdown: str, position: int) -> str:
    heading = ""
    for line in markdown[:position].splitlines():
        match = _HEADING_RE.match(line)
        if match:
            heading = _plain_markdown(match.group(1))
    return heading


def _artifact_by_filename(frame_artifacts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for artifact in frame_artifacts:
        if not isinstance(artifact, dict):
            continue
        filename = Path(_text(artifact.get("filename"))).name
        if filename:
            indexed[filename] = artifact
    return indexed


def _image_target_name(target: str) -> str:
    parsed = urlparse(_text(target))
    query_file = parse_qs(parsed.query).get("file", [""])[0]
    if query_file:
        return Path(unquote(query_file)).name
    return Path(unquote(parsed.path or target)).name


def build_visual_evidence_from_note_images(
    markdown: str,
    frame_artifacts: list[dict[str, Any]],
    *,
    provider: str | None = None,
) -> dict[str, Any]:
    """Promote note image references into final visual evidence.

    Raw candidate frames are not enough to become screenshots in notes. This
    function only promotes frames when the generated note explicitly references
    them with Markdown image syntax and provides a non-empty alt text.
    """
    artifact_index = _artifact_by_filename(frame_artifacts)
    evidence: list[dict[str, Any]] = []
    visual_artifacts: dict[str, dict[str, Any]] = {}

    for match in _IMAGE_RE.finditer(markdown or ""):
        alt_text = _plain_markdown(match.group(1))
        image_name = _image_target_name(match.group(2))
        artifact = artifact_index.get(image_name)
        if not alt_text or not artifact:
            continue
        visual_id = f"visual_{len(evidence) + 1:03d}"
        artifact_url = _text(artifact.get("url"))
        timestamp = artifact.get("timestamp_seconds")
        artifact_provider = _text(provider or artifact.get("provider"))
        visual_artifacts[visual_id] = {
            **artifact,
            "kind": visual_id,
            "content_type": artifact.get("content_type") or "image/jpeg",
            "timestamp_seconds": timestamp,
            "provider": artifact_provider or None,
        }
        evidence.append({
            "id": visual_id,
            "timestamp_seconds": timestamp,
            "reason": alt_text,
            "note_section": _heading_before(markdown, match.start()),
            "source": "visual_review_grid",
            "confidence": "high",
            "provider": artifact_provider or None,
            "artifact_kind": visual_id,
            "artifact_url": artifact_url,
        })

    return {
        "visual_evidence": [
            {key: value for key, value in item.items() if value not in (None, "")}
            for item in evidence
        ],
        "visual_artifacts": {
            key: {field: value for field, value in artifact.items() if value not in (None, "")}
            for key, artifact in visual_artifacts.items()
        },
        "visual_evidence_status": "completed" if evidence else "unavailable",
        "visual_evidence_reason": (
            "多模态 Agent 已在笔记中选择截图并提供图注。"
            if evidence
            else "没有可确认的截图证据；候选帧不会自动插入笔记。"
        ),
    }


def rewrite_note_image_references(markdown: str, frame_artifacts: list[dict[str, Any]]) -> str:
    artifact_index = _artifact_by_filename(frame_artifacts)

    def replace(match: re.Match[str]) -> str:
        alt_text = match.group(1)
        raw_target = _text(match.group(2))
        artifact = artifact_index.get(Path(raw_target).name)
        artifact_url = _text((artifact or {}).get("url"))
        if not artifact_url:
            return match.group(0)
        return f"![{alt_text}]({artifact_url})"

    return _IMAGE_RE.sub(replace, markdown or "")


__all__ = ["build_visual_evidence_from_note_images", "rewrite_note_image_references"]
