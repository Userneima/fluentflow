from backend.core.transcript_cleaner import clean_repeated_transcript


def test_collapse_obvious_repeated_phrase_loop():
    repeated = " ".join(["用户体验"] * 14)
    result = clean_repeated_transcript([
        {"start": 1.0, "end": 8.0, "text": repeated},
    ])

    assert result.cleaned_text == "用户体验"
    assert result.applied_count == 1
    assert result.issues[0].kind == "repeated_phrase"
    assert result.issues[0].repeat_unit == "用户体验"
    assert result.issues[0].repeat_count == 14


def test_collapse_repeated_phrase_without_spaces():
    result = clean_repeated_transcript([
        {"start": 0.0, "end": 4.0, "text": "进去进去进去进去进去进去进去"},
    ])

    assert result.cleaned_text == "进去"
    assert result.applied_count == 1


def test_collapse_repeated_segments_run():
    result = clean_repeated_transcript([
        {"start": 0.0, "end": 1.0, "text": "用户体验很重要"},
        {"start": 1.0, "end": 2.0, "text": "用户体验很重要"},
        {"start": 2.0, "end": 3.0, "text": "用户体验很重要"},
        {"start": 3.0, "end": 4.0, "text": "后面继续讲产品设计"},
    ])

    assert [item["text"] for item in result.cleaned_segments] == [
        "用户体验很重要",
        "后面继续讲产品设计",
    ]
    assert result.removed_segment_count == 2
    assert result.issues[0].kind == "repeated_segments"
    assert result.cleaned_segments[0]["end"] == 3.0


def test_short_natural_repetition_is_preserved():
    result = clean_repeated_transcript([
        {"start": 0.0, "end": 1.0, "text": "用户体验 用户体验 这个词今天会反复出现"},
    ])

    assert result.cleaned_text == "用户体验 用户体验 这个词今天会反复出现"
    assert result.applied_count == 0
