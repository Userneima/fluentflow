"""Tests for AI summarizer provider selection."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.core.ai_summarizer import (
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_OPENAI_MODEL,
    _normalize_provider,
    _provider_api_key,
    _provider_base_url,
    _provider_default_model,
)


class TestAiSummarizer(unittest.TestCase):
    def test_normalize_provider_defaults_to_deepseek(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_normalize_provider(None), "deepseek")

    def test_normalize_provider_accepts_openai(self) -> None:
        self.assertEqual(_normalize_provider("OpenAI"), "openai")

    def test_normalize_provider_rejects_unknown(self) -> None:
        with self.assertRaises(ValueError):
            _normalize_provider("unknown")

    def test_provider_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_provider_default_model("deepseek"), DEFAULT_DEEPSEEK_MODEL)
            self.assertEqual(_provider_default_model("openai"), DEFAULT_OPENAI_MODEL)
            self.assertEqual(_provider_base_url("deepseek"), "https://api.deepseek.com")
            self.assertEqual(_provider_base_url("openai"), "https://api.openai.com/v1")

    def test_provider_api_key_uses_matching_env(self) -> None:
        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "deepseek-key", "OPENAI_API_KEY": "openai-key"},
            clear=True,
        ):
            self.assertEqual(_provider_api_key("deepseek"), "deepseek-key")
            self.assertEqual(_provider_api_key("openai"), "openai-key")


if __name__ == "__main__":
    unittest.main()
