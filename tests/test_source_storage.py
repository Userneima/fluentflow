from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from backend.core.server_helpers import _find_source_file, _persist_source_file


def test_persist_and_find_source_file(tmp_path: Path) -> None:
    with patch.dict("os.environ", {"FLUENTFLOW_SOURCE_DIR": str(tmp_path)}):
        saved = _persist_source_file("task-source", ".mp3", b"audio")
        found = _find_source_file("task-source")

    assert saved.name == "source.mp3"
    assert found == saved
    assert found.read_bytes() == b"audio"
