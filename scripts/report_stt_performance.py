#!/usr/bin/env python3
"""Summarize FluentFlow STT performance events from SQLite."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "fluentflow_events.sqlite"


def load_stt_events(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT created_at, task_id, source_filename, source_duration_seconds,
                   source_file_size_mb, duration_seconds, transcript_length,
                   success, metadata
            FROM events
            WHERE event_name = 'stt_completed'
            ORDER BY created_at
            """
        ).fetchall()
    events = []
    for row in rows:
        item = dict(row)
        try:
            item["metadata"] = json.loads(item.get("metadata") or "{}")
        except json.JSONDecodeError:
            item["metadata"] = {}
        meta = item["metadata"]
        factor = meta.get("stt_realtime_factor")
        if factor is None and item.get("source_duration_seconds"):
            factor = item["duration_seconds"] / item["source_duration_seconds"]
        item["stt_realtime_factor"] = factor
        events.append(item)
    return events


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    factors = [
        e["stt_realtime_factor"]
        for e in events
        if isinstance(e.get("stt_realtime_factor"), (int, float))
    ]
    duration_sum = sum(e.get("source_duration_seconds") or 0 for e in events)
    stt_sum = sum(e.get("duration_seconds") or 0 for e in events)

    def group_key(event: dict[str, Any]) -> tuple[str, str, str, str, str]:
        meta = event.get("metadata") or {}
        return (
            str(meta.get("runtime_os") or "unknown"),
            str(meta.get("runtime_machine") or "unknown"),
            str(meta.get("stt_model") or "unknown"),
            str(meta.get("stt_speed") or "unknown"),
            str(meta.get("stt_language") or "unknown"),
        )

    grouped: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[group_key(event)].append(event)

    group_rows = []
    for key, rows in sorted(grouped.items()):
        row_duration_sum = sum(r.get("source_duration_seconds") or 0 for r in rows)
        row_stt_sum = sum(r.get("duration_seconds") or 0 for r in rows)
        row_factor = row_stt_sum / row_duration_sum if row_duration_sum else None
        group_rows.append({
            "runtime_os": key[0],
            "runtime_machine": key[1],
            "stt_model": key[2],
            "stt_speed": key[3],
            "stt_language": key[4],
            "sample_count": len(rows),
            "source_duration_seconds": round(row_duration_sum, 3),
            "stt_elapsed_seconds": round(row_stt_sum, 3),
            "weighted_realtime_factor": round(row_factor, 4) if row_factor else None,
            "weighted_realtime_speed": round(1 / row_factor, 3) if row_factor else None,
        })

    same_source_runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        fp = ((event.get("metadata") or {}).get("source_fingerprint") or {}).get("sha256")
        if fp:
            same_source_runs[fp].append(event)
    comparable_sources = {
        fp: rows
        for fp, rows in same_source_runs.items()
        if len(rows) > 1
    }

    return {
        "event_count": len(events),
        "source_duration_seconds": round(duration_sum, 3),
        "stt_elapsed_seconds": round(stt_sum, 3),
        "weighted_realtime_factor": round(stt_sum / duration_sum, 4) if duration_sum else None,
        "weighted_realtime_speed": round(duration_sum / stt_sum, 3) if stt_sum else None,
        "min_realtime_factor": round(min(factors), 4) if factors else None,
        "max_realtime_factor": round(max(factors), 4) if factors else None,
        "groups": group_rows,
        "same_source_comparison_count": len(comparable_sources),
    }


def write_markdown(summary: dict[str, Any], output: Path | None) -> None:
    speed = summary["weighted_realtime_speed"]
    lines = [
        "# FluentFlow STT Performance Report",
        "",
        f"- STT samples: {summary['event_count']}",
        f"- Total source duration: {summary['source_duration_seconds']} sec",
        f"- Total STT elapsed: {summary['stt_elapsed_seconds']} sec",
        f"- Weighted realtime factor: {summary['weighted_realtime_factor']}",
        f"- Weighted realtime speed: {speed}x" if speed is not None else "- Weighted realtime speed: unavailable",
        f"- Same-source comparison groups: {summary['same_source_comparison_count']}",
        "",
        "## Groups",
        "",
        "| Runtime | Model | Speed | Language | Samples | Duration sec | STT sec | Factor | Speed |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary["groups"]:
        runtime = f"{row['runtime_os']} / {row['runtime_machine']}"
        lines.append(
            f"| {runtime} | {row['stt_model']} | {row['stt_speed']} | {row['stt_language']} | "
            f"{row['sample_count']} | {row['source_duration_seconds']} | {row['stt_elapsed_seconds']} | "
            f"{row['weighted_realtime_factor']} | "
            f"{str(row['weighted_realtime_speed']) + 'x' if row['weighted_realtime_speed'] is not None else 'unavailable'} |"
        )
    text = "\n".join(lines) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--format", choices=("json", "md"), default="md")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    summary = summarize(load_stt_events(args.db))
    if args.format == "json":
        text = json.dumps(summary, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
    else:
        write_markdown(summary, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
