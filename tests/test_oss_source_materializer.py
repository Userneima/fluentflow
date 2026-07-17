from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.oss_source_materializer import materialize_oss_source


class ChunkedDownloader:
    def __init__(self, chunks: list[bytes], reported_size: int | None = None):
        self.chunks = chunks
        self.reported_size = reported_size

    def download_to_file(self, *, object_key: str, target_path: Path) -> int:
        with target_path.open("wb") as target:
            for chunk in self.chunks:
                target.write(chunk)
        return self.reported_size if self.reported_size is not None else sum(map(len, self.chunks))


def test_materialize_oss_source_writes_atomically_to_task_source_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    source = materialize_oss_source(
        ChunkedDownloader([b"first", b"-", b"second"]),
        task_id="task-1",
        object_key="uploads/source/private/source.mp4",
        suffix=".mp4",
        expected_size_bytes=12,
    )

    assert source == tmp_path / "sources" / "task-1" / "source.mp4"
    assert source.read_bytes() == b"first-second"
    assert not list(source.parent.glob("*.part"))


def test_materialize_oss_source_rejects_size_mismatch_without_final_source(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))

    with pytest.raises(RuntimeError, match="size verification"):
        materialize_oss_source(
            ChunkedDownloader([b"short"], reported_size=5),
            task_id="task-2",
            object_key="uploads/source/private/source.mp4",
            suffix=".mp4",
            expected_size_bytes=6,
        )

    task_dir = tmp_path / "sources" / "task-2"
    assert not (task_dir / "source.mp4").exists()
    assert not list(task_dir.glob("*.part"))
