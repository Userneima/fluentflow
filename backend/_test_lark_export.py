from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# ensure repository root is importable when running the script from backend/
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv()

from backend.core.lark_exporter import export_markdown_to_lark

TITLE = "FluentFlow Test Doc"
MD = "# Test\n\nThis is a small test document created by the FluentFlow test script.\n"

try:
    resp = export_markdown_to_lark(TITLE, MD)
    print(json.dumps({"ok": True, "response": resp}, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e)}))
