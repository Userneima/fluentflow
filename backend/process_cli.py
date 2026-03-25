"""Tiny CLI to run the pipeline outside of the ASGI server.

Usage:
    python -m backend.process_cli /path/to/video.mp4 --export-to-lark

This mirrors the logic in `backend.main:__main__` but provides a small entry
point for developers who prefer a script.
"""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    from backend.core.audio_handler import extract_compressed_mp3
    from backend.core.local_stt import transcribe_audio
    from backend.core.ai_summarizer import summarize_transcript_to_markdown
    from backend.core.lark_exporter import export_markdown_to_lark
except ImportError:
    from core.audio_handler import extract_compressed_mp3
    from core.local_stt import transcribe_audio
    from core.ai_summarizer import summarize_transcript_to_markdown
    from core.lark_exporter import export_markdown_to_lark


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="Path to local video file")
    parser.add_argument("--export-to-lark", action="store_true")
    parser.add_argument("--title", default=None)
    parser.add_argument("--folder-token", default=None)
    args = parser.parse_args()

    vp = Path(args.video)
    if not vp.is_file():
        raise SystemExit(f"video not found: {vp}")

    print("Extracting audio...")
    mp3 = extract_compressed_mp3(vp)
    print("Running STT...")
    tr = transcribe_audio(mp3)
    print("Summarizing...")
    try:
        md = summarize_transcript_to_markdown(tr.text)
    except Exception:
        md = f"# Transcript\n\n{tr.text}"

    print("--- SUMMARY PREVIEW ---")
    print(md[:2000])

    if args.export_to_lark:
        print("Exporting to Lark...")
        out = export_markdown_to_lark(args.title or vp.stem, md, folder_token=args.folder_token)
        print("Lark response:", out)


if __name__ == "__main__":
    main()
