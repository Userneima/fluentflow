"""Lark / Feishu exporter: create a document and write Markdown content as blocks."""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://open.larksuite.com"

# Feishu docx block types (official enum from API docs)
_BT_TEXT = 2
_BT_H1 = 3
_BT_H2 = 4
_BT_H3 = 5
_BT_H4 = 6
_BT_H5 = 7
_BT_H6 = 8
_BT_BULLET = 12
_BT_ORDERED = 13
_BT_CODE = 14
_BT_QUOTE = 15
_BT_TODO = 17
_BT_DIVIDER = 22

_HEADING_FIELD = {3: "heading1", 4: "heading2", 5: "heading3",
                  6: "heading4", 7: "heading5", 8: "heading6"}

_MAX_BLOCKS_PER_BATCH = 50


# ---------------------------------------------------------------------------
# Markdown → Feishu block dicts
# ---------------------------------------------------------------------------

def _parse_inline(text: str) -> List[dict]:
    """Parse **bold** into a list of Feishu TextElement dicts."""
    parts = text.split("**")
    elements: List[dict] = []
    for idx, part in enumerate(parts):
        if not part:
            continue
        style: dict = {"bold": True} if idx % 2 == 1 else {}
        elements.append({"text_run": {"content": part, "text_element_style": style}})
    return elements or [{"text_run": {"content": text, "text_element_style": {}}}]


def _text_body(text: str) -> dict:
    return {"elements": _parse_inline(text), "style": {}}


def _text_block(text: str) -> dict:
    return {"block_type": _BT_TEXT, "text": _text_body(text)}


def _heading_block(text: str, level: int) -> dict:
    bt = _BT_H1 + level - 1
    field = _HEADING_FIELD.get(bt, "heading1")
    return {"block_type": bt, field: _text_body(text)}


def _bullet_block(text: str) -> dict:
    return {"block_type": _BT_BULLET, "bullet": _text_body(text)}


def _ordered_block(text: str) -> dict:
    return {"block_type": _BT_ORDERED, "ordered": _text_body(text)}


def _code_block(code: str) -> dict:
    return {
        "block_type": _BT_CODE,
        "code": {
            "elements": [{"text_run": {"content": code, "text_element_style": {}}}],
            "style": {},
            "language": 1,
        },
    }


_RE_ORDERED = re.compile(r"^\d+[.）]\s+(.+)")


def markdown_to_feishu_blocks(markdown: str) -> List[dict]:
    """Convert a Markdown string to a flat list of Feishu block dicts."""
    blocks: List[dict] = []
    lines = markdown.split("\n")
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # fenced code block
        if stripped.startswith("```"):
            code_lines: list[str] = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1  # skip closing ```
            blocks.append(_code_block("\n".join(code_lines)))
            continue

        # headings (check longer prefixes first)
        if stripped.startswith("###### "):
            blocks.append(_heading_block(stripped[7:], 6))
        elif stripped.startswith("##### "):
            blocks.append(_heading_block(stripped[6:], 5))
        elif stripped.startswith("#### "):
            blocks.append(_heading_block(stripped[5:], 4))
        elif stripped.startswith("### "):
            blocks.append(_heading_block(stripped[4:], 3))
        elif stripped.startswith("## "):
            blocks.append(_heading_block(stripped[3:], 2))
        elif stripped.startswith("# "):
            blocks.append(_heading_block(stripped[2:], 1))

        # unordered list
        elif stripped.startswith("- ") or stripped.startswith("* "):
            blocks.append(_bullet_block(stripped[2:]))

        # ordered list
        elif (m := _RE_ORDERED.match(stripped)):
            blocks.append(_ordered_block(m.group(1)))

        # blockquote
        elif stripped.startswith("> "):
            blocks.append({"block_type": _BT_QUOTE, "quote": _text_body(stripped[2:])})

        # divider
        elif stripped in ("---", "***", "___"):
            blocks.append({"block_type": _BT_DIVIDER})

        # regular paragraph
        else:
            blocks.append(_text_block(stripped))

        i += 1

    return blocks


# ---------------------------------------------------------------------------
# Low-level Feishu HTTP helpers (avoids SDK model-version issues for blocks)
# ---------------------------------------------------------------------------

def _get_tenant_token(app_id: str, app_secret: str, base_url: str, timeout: int = 15) -> str:
    url = f"{base_url}/open-apis/auth/v3/tenant_access_token/internal"
    body = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json; charset=utf-8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    if data.get("code") != 0:
        raise RuntimeError(f"Feishu tenant token error: {data}")
    return data["tenant_access_token"]


def _post_block_children(
    token: str, base_url: str, doc_id: str, blocks: List[dict], timeout: int = 15,
) -> dict:
    url = f"{base_url}/open-apis/docx/v1/documents/{doc_id}/blocks/{doc_id}/children"
    body = json.dumps({"children": blocks, "index": -1}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# LarkExporter
# ---------------------------------------------------------------------------

class LarkExporter:
    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: int = 15,
        dry_run: bool = False,
    ) -> None:
        load_dotenv()
        self.app_id = app_id or os.environ.get("LARK_APP_ID")
        self.app_secret = app_secret or os.environ.get("LARK_APP_SECRET")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.dry_run = bool(dry_run)

    def _require_creds(self) -> None:
        if not (self.app_id and self.app_secret):
            raise ValueError(
                "Lark credentials not set: provide app_id/app_secret or "
                "set LARK_APP_ID and LARK_APP_SECRET"
            )

    def _build_sdk_client(self):
        import lark_oapi as lark
        return lark.Client.builder() \
            .app_id(self.app_id) \
            .app_secret(self.app_secret) \
            .domain(self.base_url) \
            .build()

    def _create_empty_doc(self, title: str, folder_token: Optional[str]) -> str:
        """Create an empty document via SDK; return document_id."""
        from lark_oapi.api.docx.v1.model import (
            CreateDocumentRequest,
            CreateDocumentRequestBody,
        )
        client = self._build_sdk_client()
        rb = CreateDocumentRequestBody.builder().title(title)
        if folder_token:
            rb = rb.folder_token(folder_token)
        request = CreateDocumentRequest.builder().request_body(rb.build()).build()

        response = client.docx.v1.document.create(request)
        if not response.success():
            raise RuntimeError(
                f"Lark create-doc error: code={response.code}, msg={response.msg}"
            )
        doc = response.data.document
        if not doc or not doc.document_id:
            raise RuntimeError("Lark returned no document_id")
        return doc.document_id

    def _get_token(self) -> str:
        return _get_tenant_token(
            self.app_id, self.app_secret, self.base_url, self.timeout
        )

    def _write_blocks(self, token: str, doc_id: str, blocks: List[dict]) -> None:
        """Batch-write blocks into a Feishu document using raw HTTP."""
        if not blocks:
            return
        for start in range(0, len(blocks), _MAX_BLOCKS_PER_BATCH):
            batch = blocks[start : start + _MAX_BLOCKS_PER_BATCH]
            try:
                result = _post_block_children(
                    token, self.base_url, doc_id, batch, self.timeout
                )
                if result.get("code") != 0:
                    logger.warning(
                        "Feishu block write error (batch %d): code=%s msg=%s",
                        start // _MAX_BLOCKS_PER_BATCH,
                        result.get("code"),
                        result.get("msg"),
                    )
            except Exception:
                logger.exception("Failed to write block batch starting at %d", start)

    def _set_link_sharing(self, token: str, doc_id: str) -> None:
        """Make the document accessible to anyone in the organization via link."""
        url = (
            f"{self.base_url}/open-apis/drive/v1/permissions"
            f"/{doc_id}/public?type=docx"
        )
        body = json.dumps({
            "external_access_entity": "closed",
            "security_entity": "anyone_can_view",
            "comment_entity": "anyone_can_view",
            "share_entity": "anyone",
            "link_share_entity": "tenant_editable",
        }).encode()
        req = urllib.request.Request(url, data=body, method="PATCH", headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
            if data.get("code") != 0:
                logger.warning("Failed to set link sharing: %s", data)
        except Exception:
            logger.exception("Failed to set link sharing for %s", doc_id)

    def create_doc_markdown(
        self,
        title: str,
        markdown: str,
        folder_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a Feishu document and populate it with parsed Markdown content."""
        self._require_creds()

        if self.dry_run:
            blocks = markdown_to_feishu_blocks(markdown)
            logger.info(
                "Dry-run: would create doc '%s' (%d blocks) in folder '%s'",
                title, len(blocks), folder_token,
            )
            return {"ok": True, "dry_run": True, "title": title, "block_count": len(blocks)}

        doc_id = self._create_empty_doc(title, folder_token)
        token = self._get_token()
        blocks = markdown_to_feishu_blocks(markdown)
        self._write_blocks(token, doc_id, blocks)
        self._set_link_sharing(token, doc_id)

        return {
            "ok": True,
            "doc_token": doc_id,
            "block_count": len(blocks),
            "url": f"https://feishu.cn/docx/{doc_id}",
        }


def export_markdown_to_lark(
    title: str,
    markdown: str,
    *,
    app_id: Optional[str] = None,
    app_secret: Optional[str] = None,
    folder_token: Optional[str] = None,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = 15,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Convenience wrapper used by the pipeline."""
    exporter = LarkExporter(
        app_id=app_id,
        app_secret=app_secret,
        base_url=base_url,
        timeout=timeout,
        dry_run=dry_run,
    )
    return exporter.create_doc_markdown(title, markdown, folder_token=folder_token)


__all__ = ["LarkExporter", "export_markdown_to_lark", "markdown_to_feishu_blocks"]
