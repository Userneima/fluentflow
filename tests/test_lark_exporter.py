"""Unit tests for backend.core.lark_exporter using unittest.mock."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch, MagicMock

from backend.core.lark_exporter import LarkExporter, export_markdown_to_lark


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


if __name__ == "__main__":
    unittest.main()