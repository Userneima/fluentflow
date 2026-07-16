from __future__ import annotations

from backend.core.elevenlabs_usage import _tabular_rows


def test_tabular_analytics_rows_preserve_named_columns() -> None:
    rows = _tabular_rows({
        "columns": ["timestamp", "product_type", "credits_used"],
        "rows": [["2026-07-16T08:00:00Z", "speech_to_text", "873"]],
    })

    assert rows == [{
        "timestamp": "2026-07-16T08:00:00Z",
        "product_type": "speech_to_text",
        "credits_used": "873",
    }]
