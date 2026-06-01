"""Lark / Feishu exporter: create a document and write Markdown content as blocks."""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# 国际版 Lark 默认域名；国内飞书企业应用请设环境变量 LARK_OPEN_BASE_URL=https://open.feishu.cn
DEFAULT_BASE_URL = "https://open.larksuite.com"

# Feishu docx block types
# Official SDK models expose heading1~heading9, then bullet/ordered/code.
# That means:
#   text=2, heading1~heading9=3..11, bullet=12, ordered=13, code=14, divider=22.
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
        run: dict = {"content": part}
        if idx % 2 == 1:
            run["text_element_style"] = {"bold": True}
        elements.append({"text_run": run})
    return elements or [{"text_run": {"content": text}}]


def _text_body(text: str) -> dict:
    return {"elements": _parse_inline(text)}


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
    return {"block_type": _BT_CODE, "code": _text_body(code)}


_RE_ORDERED = re.compile(r"^\d+[.）]\s+(.+)")
_RE_MD_TABLE_ALIGN = re.compile(
    r"^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?$"
)


def _looks_like_markdown_table(lines: List[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    head = lines[index].strip()
    align = lines[index + 1].strip()
    if "|" not in head or "|" not in align:
        return False
    return bool(_RE_MD_TABLE_ALIGN.match(align))


def markdown_contains_table(markdown: str) -> bool:
    lines = markdown.split("\n")
    return any(_looks_like_markdown_table(lines, i) for i in range(len(lines) - 1))


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

        # blockquote → render as italic paragraph with "❝" prefix
        elif stripped.startswith("> "):
            blocks.append(_text_block("❝ " + stripped[2:]))

        # divider
        elif stripped in ("---", "***", "___"):
            blocks.append({"block_type": _BT_DIVIDER, "divider": {}})

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


def _public_docx_url(doc_id: str, base_url: str) -> str:
    """Browser URL for the docx; depends on tenant (China vs international)."""
    b = (base_url or "").lower()
    if "open.feishu.cn" in b or "feishu.cn" in b:
        return f"https://feishu.cn/docx/{doc_id}"
    return f"https://larksuite.com/docx/{doc_id}"


def _convert_markdown_via_openapi(
    token: str, base_url: str, markdown: str, timeout: int
) -> dict:
    """POST /docx/v1/documents/blocks/convert — returns official block tree."""
    url = f"{base_url.rstrip('/')}/open-apis/docx/v1/documents/blocks/convert"
    body = json.dumps(
        {"content_type": "markdown", "content": markdown or ""},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            err = json.loads(raw)
        except Exception:
            raise RuntimeError(f"Feishu convert HTTP {e.code}: {raw[:1200]}") from e
        raise RuntimeError(f"Feishu convert HTTP {e.code}: {err}") from e
    if data.get("code") != 0:
        raise RuntimeError(
            f"Feishu Markdown→blocks 失败（请检查应用是否开通 docx:document.block:convert 等权限）: {data}"
        )
    return data.get("data") or {}


def _block_to_create_payload(b: dict, by_id: Dict[str, dict]) -> dict:
    """Strip server-side ids and rebuild nested children for create-children API."""
    out = {k: v for k, v in b.items() if k not in ("block_id", "parent_id")}
    cids = b.get("children")
    if cids and isinstance(cids, list) and len(cids) > 0 and isinstance(cids[0], str):
        out["children"] = [
            _block_to_create_payload(by_id[cid], by_id) for cid in cids if cid in by_id
        ]
    else:
        out.pop("children", None)
    tbl = out.get("table")
    if isinstance(tbl, dict):
        # `cells` in convert output references server-generated block ids,
        # which are invalid when creating a new document. The nested `children`
        # payload already preserves the table cell structure.
        tbl.pop("cells", None)
        prop = tbl.get("property")
        if isinstance(prop, dict):
            # Merge metadata is server-generated in convert output. For
            # Markdown tables without merged cells we can omit it safely.
            prop.pop("merge_info", None)
    return out


def _convert_data_to_root_children(data: dict) -> List[dict]:
    """Use first_level_block_ids + blocks from convert response."""
    blocks = data.get("blocks") or []
    if not blocks:
        return []
    by_id: Dict[str, dict] = {}
    for b in blocks:
        bid = b.get("block_id")
        if bid:
            by_id[str(bid)] = b
    first_ids = data.get("first_level_block_ids") or []
    if not first_ids:
        # 极少数返回无 first_level：若均为扁平块则按数组顺序作为根
        if all(not (x.get("children") or []) for x in blocks):
            return [_block_to_create_payload(x, by_id) for x in blocks if x.get("block_id")]
        raise ValueError("convert response missing first_level_block_ids")
    return [
        _block_to_create_payload(by_id[str(bid)], by_id)
        for bid in first_ids
        if str(bid) in by_id
    ]


def _post_block_children(
    token: str,
    base_url: str,
    doc_id: str,
    blocks: List[dict],
    timeout: int = 15,
    *,
    document_revision_id: int = -1,
) -> dict:
    # -1 = 操作文档最新版本（飞书文档；首批写入建议显式带上）
    qs: Dict[str, Union[int, str]] = {"document_revision_id": document_revision_id}
    query = "?" + urlencode(qs)
    url = (
        f"{base_url.rstrip('/')}/open-apis/docx/v1/documents/{doc_id}/"
        f"blocks/{doc_id}/children{query}"
    )
    body = json.dumps({"children": blocks}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            err = json.loads(raw)
        except Exception:
            raise RuntimeError(f"Feishu 写入块 HTTP {e.code}: {raw[:1200]}") from e
        raise RuntimeError(f"Feishu 写入块 HTTP {e.code}: {err}") from e


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
        env_base = (os.environ.get("LARK_OPEN_BASE_URL") or "").strip()
        if env_base:
            self.base_url = env_base.rstrip("/")
        else:
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

    def _write_root_blocks_batched(self, doc_id: str, token: str, root_children: List[dict]) -> None:
        """Append root-level blocks (may nest children) in batches; fail on API error."""
        if not root_children:
            raise RuntimeError("没有可写入的文档块（内容为空）")
        rev: Optional[int] = None
        t = max(self.timeout, 90)
        for start in range(0, len(root_children), _MAX_BLOCKS_PER_BATCH):
            batch = root_children[start : start + _MAX_BLOCKS_PER_BATCH]
            doc_rev = -1 if rev is None else rev
            result = _post_block_children(
                token,
                self.base_url,
                doc_id,
                batch,
                t,
                document_revision_id=doc_rev,
            )
            if result.get("code") != 0:
                raise RuntimeError(
                    f"Feishu 写入块失败: code={result.get('code')} msg={result.get('msg')} body={result}"
                )
            data = result.get("data") or {}
            r = data.get("document_revision_id")
            if r is not None:
                rev = int(r)

    def _write_flat_blocks_batched(self, doc_id: str, token: str, blocks: List[dict]) -> None:
        """Legacy flat blocks from markdown_to_feishu_blocks; fail on API error."""
        if not blocks:
            return
        t = max(self.timeout, 90)
        rev: Optional[int] = None
        for start in range(0, len(blocks), _MAX_BLOCKS_PER_BATCH):
            batch = blocks[start : start + _MAX_BLOCKS_PER_BATCH]
            doc_rev = -1 if rev is None else rev
            result = _post_block_children(
                token,
                self.base_url,
                doc_id,
                batch,
                t,
                document_revision_id=doc_rev,
            )
            if result.get("code") != 0:
                raise RuntimeError(
                    f"Feishu 写入块失败: code={result.get('code')} msg={result.get('msg')} body={result}"
                )
            data = result.get("data") or {}
            r = data.get("document_revision_id")
            if r is not None:
                rev = int(r)

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
        token = _get_tenant_token(
            self.app_id, self.app_secret, self.base_url, self.timeout
        )
        conv_timeout = max(self.timeout, 90)
        # 默认走内置扁平块写入；官方 convert 的嵌套块在单次 create-children 中易被忽略导致「空文档」。
        # 若需实验 OpenAPI 转换，可设置 FLUENTFLOW_LARK_USE_OPENAPI_CONVERT=1
        wants_convert = (
            os.environ.get("FLUENTFLOW_LARK_USE_OPENAPI_CONVERT", "").strip().lower()
            in ("1", "true", "yes", "on")
        )
        if markdown_contains_table(markdown):
            wants_convert = True
        used_convert = False
        root_children: List[dict] = []
        if wants_convert:
            try:
                conv_data = _convert_markdown_via_openapi(
                    token, self.base_url, markdown, conv_timeout
                )
                root_children = _convert_data_to_root_children(conv_data)
                used_convert = bool(root_children)
            except Exception as exc:
                logger.warning(
                    "Feishu Markdown→blocks 官方转换失败，改用内置解析: %s",
                    exc,
                )

        if used_convert:
            self._write_root_blocks_batched(doc_id, token, root_children)
            block_count = len(root_children)
        else:
            flat = markdown_to_feishu_blocks(markdown)
            self._write_flat_blocks_batched(doc_id, token, flat)
            block_count = len(flat)

        md_nonempty = bool((markdown or "").strip())
        if md_nonempty and block_count == 0:
            raise RuntimeError(
                "摘要内容未能解析为飞书文档块（0 块）。请检查 Markdown 是否为空或仅含不支持的语法。"
            )

        return {
            "ok": True,
            "doc_token": doc_id,
            "block_count": block_count,
            "via": "openapi_convert" if used_convert else "legacy_markdown",
            "url": _public_docx_url(doc_id, self.base_url),
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
