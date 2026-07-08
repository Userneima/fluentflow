# Feishu Export Format Reference

This document records the official Feishu/Lark document-format facts that
FluentFlow export code must follow. It is intentionally narrow: it covers
turning FluentFlow's note Markdown into a Feishu docx document without leaking
raw Markdown syntax into the final document.

## Official Sources

- Feishu Open Platform: Markdown/HTML content to document blocks
  `https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/document-docx/docx-v1/document/convert`
- Feishu Open Platform: Block data structure
  `https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/document-docx/docx-v1/data-structure/block`
- Feishu Open Platform: Create nested blocks
  `https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/document-docx/docx-v1/document-block-descendant/create`
- Feishu Open Platform: Create blocks
  `https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document-block/create`

The official docs expose Markdown versions by appending `.md` to these URLs.
Use those Markdown pages when refreshing this reference.

## Official Model

Feishu docx documents are block trees. A `Document` is rooted at a page block;
content is represented as `Block` objects with `block_type`, optional
type-specific payload, and `children`.

For FluentFlow note export, the important block types are:

| Meaning | Block type | Payload |
| --- | ---: | --- |
| Text | 2 | `text` |
| Heading 1-9 | 3-11 | `heading1` ... `heading9` |
| Bullet list | 12 | `bullet` |
| Ordered list | 13 | `ordered` |
| Code block | 14 | `code` |
| Quote | 15 | `quote` |
| Todo | 17 | `todo` |
| Divider | 22 | `divider` |
| Image | 27 | `image` |
| Table | 31 | `table` |
| Table cell | 32 | `table_cell` |

## Official Markdown Import Flow

The official route for Markdown/HTML import is:

1. Create a docx document.
2. Call `POST /open-apis/docx/v1/documents/blocks/convert` with
   `{"content_type": "markdown", "content": "..."}`.
3. Insert returned blocks with
   `POST /open-apis/docx/v1/documents/:document_id/blocks/:block_id/descendant`.

Do not treat Feishu as a CommonMark renderer. The conversion API is the contract
for Feishu-compatible Markdown import.

## Table Rules

The conversion API supports Markdown tables and returns Table / TableCell
blocks. For tables:

- Use the nested block endpoint, not the simple children endpoint.
- Before inserting converted Table blocks, remove the table `merge_info` field.
  The official docs call it a read-only property; sending it can cause errors.
- Do not pass server-generated table `cells` metadata back into create requests;
  the block tree is represented by `children`.
- `children_id` in the nested-block request contains only first-level child
  block IDs.
- `descendants` contains the flat list of all blocks to create, including table
  cells and text children.

## Image Rules

The conversion API can return Image blocks. After inserting image blocks, the
official flow requires:

1. Upload the image file as `docx_image` with the Image block ID as
   `parent_node`.
2. Patch or batch-update the Image block with `replace_image`.

FluentFlow already does this for artifact images in the flat-block fallback.
The official convert path must preserve the same behavior when image upload is
enabled there.

## Fallback Policy

FluentFlow may use a fallback only when the official convert path is unavailable
or fails, for example missing `docx:document.block:convert` permission.

Fallback behavior:

- Keep the original `summary_markdown` unchanged.
- Generate a Feishu-export-only Markdown copy.
- Convert fragile pipe tables into labeled lists so raw `| --- |` table source
  is not displayed in the final Feishu document. This includes loose pipe
  tables that omit the `| --- |` alignment row (two or more consecutive pipe
  rows with a consistent column count): the frontend Word/PDF exporters already
  render those as tables, so the fallback converts them too and treats the
  first row as the header labels.
- Mark the response with the export path, such as `openapi_convert`,
  `legacy_markdown`, or `lark_cli`.

## Implementation Contract

- `summary_markdown` remains the canonical product note for editor, Markdown
  download, PDF rendering, Agent API, and MCP package reads.
- Feishu export creates a separate Feishu-compatible representation at export
  time.
- User OAuth and tenant OpenAPI routes should prefer official convert +
  descendant insertion.
- Local `lark-cli` export cannot call FluentFlow's OpenAPI block writer, so it
  uses the fallback Markdown normalization before invoking `lark-cli docs
  +create`.
- Any future change to Feishu export format should update this document and
  tests in the same work unit.
