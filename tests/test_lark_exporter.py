"""Unit tests for backend.core.lark_exporter using unittest.mock."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch, MagicMock

from backend.core.lark_exporter import (
    LarkExporter,
    _convert_data_to_root_children,
    export_markdown_to_lark,
    markdown_contains_table,
    markdown_to_feishu_blocks,
)


class TestLarkExporter(unittest.TestCase):
    def setUp(self) -> None:
        self.app_id = "cli_test"
        self.app_secret = "secret"
        self.title = "Test Doc"
        self.md = "# Hello\nThis is a test."

    def test_dry_run(self) -> None:
        exporter = LarkExporter(app_id=self.app_id, app_secret=self.app_secret, dry_run=True)
        out = exporter.create_doc_markdown(self.title, self.md)
        self.assertTrue(out.get("dry_run"))
        self.assertEqual(out.get("title"), self.title)

    def test_missing_credentials(self) -> None:
        with patch.dict(os.environ, {"LARK_APP_ID": "", "LARK_APP_SECRET": ""}):
            exporter = LarkExporter()
            with self.assertRaises(ValueError) as ctx:
                exporter.create_doc_markdown(self.title, self.md)
            self.assertIn("credentials not set", str(ctx.exception))

    def test_export_markdown_to_lark_dry_run(self) -> None:
        out = export_markdown_to_lark(
            self.title,
            self.md,
            app_id=self.app_id,
            app_secret=self.app_secret,
            dry_run=True
        )
        self.assertTrue(out.get("dry_run"))

    def test_markdown_blocks_use_current_docx_block_types(self) -> None:
        blocks = markdown_to_feishu_blocks(
            "# 标题\n\n1. 第一项\n\n- 要点A\n\n```\ncode\n```\n\n***"
        )
        self.assertEqual(blocks[0]["block_type"], 3)
        self.assertEqual(blocks[1]["block_type"], 13)
        self.assertIn("ordered", blocks[1])
        self.assertEqual(blocks[2]["block_type"], 12)
        self.assertIn("bullet", blocks[2])
        self.assertEqual(blocks[3]["block_type"], 14)
        self.assertIn("code", blocks[3])
        self.assertNotIn("language", blocks[3]["code"])
        self.assertEqual(blocks[4]["block_type"], 22)
        self.assertEqual(blocks[4]["divider"], {})

    def test_markdown_contains_table_only_for_standard_table_syntax(self) -> None:
        self.assertTrue(
            markdown_contains_table(
                "| 类型 | 渠道举例 | 说明 |\n| :--- | :--- | :--- |\n| 资讯媒体 | TechCrunch | 趋势追踪 |"
            )
        )
        self.assertFalse(
            markdown_contains_table(
                "这行里有管道符 | 但不是表格\n下一行也不是表格分隔线"
            )
        )

    def test_convert_payload_rebuilds_table_without_server_side_ids(self) -> None:
        convert_data = {
            "first_level_block_ids": ["tbl_1"],
            "blocks": [
                {
                    "block_id": "tbl_1",
                    "parent_id": "doc_1",
                    "block_type": 31,
                    "children": ["cell_1", "cell_2", "cell_3", "cell_4"],
                    "table": {
                        "cells": ["cell_1", "cell_2", "cell_3", "cell_4"],
                        "property": {
                            "row_size": 2,
                            "column_size": 2,
                            "column_width": [240, 240],
                            "merge_info": [],
                        },
                    },
                },
                {
                    "block_id": "cell_1",
                    "parent_id": "tbl_1",
                    "block_type": 32,
                    "children": ["txt_1"],
                    "table_cell": {},
                },
                {
                    "block_id": "cell_2",
                    "parent_id": "tbl_1",
                    "block_type": 32,
                    "children": ["txt_2"],
                    "table_cell": {},
                },
                {
                    "block_id": "cell_3",
                    "parent_id": "tbl_1",
                    "block_type": 32,
                    "children": ["txt_3"],
                    "table_cell": {},
                },
                {
                    "block_id": "cell_4",
                    "parent_id": "tbl_1",
                    "block_type": 32,
                    "children": ["txt_4"],
                    "table_cell": {},
                },
                {
                    "block_id": "txt_1",
                    "parent_id": "cell_1",
                    "block_type": 2,
                    "text": {"elements": [{"text_run": {"content": "类型"}}]},
                },
                {
                    "block_id": "txt_2",
                    "parent_id": "cell_2",
                    "block_type": 2,
                    "text": {"elements": [{"text_run": {"content": "渠道"}}]},
                },
                {
                    "block_id": "txt_3",
                    "parent_id": "cell_3",
                    "block_type": 2,
                    "text": {"elements": [{"text_run": {"content": "资讯媒体"}}]},
                },
                {
                    "block_id": "txt_4",
                    "parent_id": "cell_4",
                    "block_type": 2,
                    "text": {"elements": [{"text_run": {"content": "TechCrunch"}}]},
                },
            ],
        }

        root_children = _convert_data_to_root_children(convert_data)
        self.assertEqual(len(root_children), 1)
        table = root_children[0]
        self.assertEqual(table["block_type"], 31)
        self.assertNotIn("block_id", table)
        self.assertNotIn("parent_id", table)
        self.assertNotIn("cells", table["table"])
        self.assertEqual(table["table"]["property"]["row_size"], 2)
        self.assertEqual(table["table"]["property"]["column_size"], 2)
        self.assertNotIn("merge_info", table["table"]["property"])
        self.assertEqual(len(table["children"]), 4)
        self.assertEqual(table["children"][0]["block_type"], 32)
        self.assertEqual(
            table["children"][0]["children"][0]["text"]["elements"][0]["text_run"]["content"],
            "类型",
        )

    @patch("backend.core.lark_exporter._convert_markdown_via_openapi")
    @patch("backend.core.lark_exporter._get_tenant_token", return_value="tenant_token")
    @patch.object(LarkExporter, "_write_flat_blocks_batched")
    @patch.object(LarkExporter, "_write_root_blocks_batched")
    @patch.object(LarkExporter, "_create_empty_doc", return_value="doc_123")
    def test_create_doc_markdown_uses_openapi_convert_for_tables(
        self,
        mock_create_doc: MagicMock,
        mock_write_root: MagicMock,
        mock_write_flat: MagicMock,
        mock_get_token: MagicMock,
        mock_convert: MagicMock,
    ) -> None:
        mock_convert.return_value = {
            "first_level_block_ids": ["tbl_1"],
            "blocks": [
                {
                    "block_id": "tbl_1",
                    "block_type": 31,
                    "children": [],
                    "table": {
                        "cells": [],
                        "property": {"row_size": 1, "column_size": 1, "merge_info": []},
                    },
                }
            ],
        }
        exporter = LarkExporter(app_id=self.app_id, app_secret=self.app_secret)

        result = exporter.create_doc_markdown(
            "表格摘要",
            "| A |\n| --- |\n| B |",
        )

        mock_create_doc.assert_called_once_with("表格摘要", None)
        mock_get_token.assert_called_once()
        mock_convert.assert_called_once()
        mock_write_root.assert_called_once()
        mock_write_flat.assert_not_called()
        self.assertEqual(result["via"], "openapi_convert")
        self.assertEqual(result["doc_token"], "doc_123")


if __name__ == "__main__":
    unittest.main()
