# STT Evaluation Workflow

FluentFlow keeps human-corrected transcripts as local evaluation assets. The goal is not to fine-tune Whisper from one sample, but to make model and prompt changes measurable.

## Local Dataset Layout

Evaluation samples live under `data/stt_eval/`, which is ignored by git because it may contain private transcripts and media.

```text
data/stt_eval/
  byte_job_share/
    reference.human_corrected.srt
    hypothesis.medium.srt
    glossary.json
    confusions.json
```

## Run Evaluation

```bash
python3 scripts/evaluate_stt.py \
  --reference data/stt_eval/byte_job_share/reference.human_corrected.srt \
  --hypothesis data/stt_eval/byte_job_share/hypothesis.medium.srt \
  --glossary data/stt_eval/byte_job_share/glossary.json \
  --confusions data/stt_eval/byte_job_share/confusions.json \
  --output-dir reports/stt_eval/byte_job_share
```

The script writes:

- `summary.json`: character accuracy, CER, segment exact rate, glossary recall, active confusion count.
- `changed_segments.tsv`: subtitle rows that differ from the human reference.
- `glossary_recall.tsv`: whether important terms in the reference also appear in the model output.
- `confusion_hits.tsv`: known wrong terms that still appear in the model output.

## Metric Meaning

- `char_accuracy`: `1 - CER`, after normalizing whitespace and punctuation. This is the main STT quality number for Chinese-heavy transcripts.
- `segment_exact_rate`: percentage of subtitle segments that need no text edit at all. This is stricter and closer to manual editing workload.
- `glossary_recall`: whether domain terms such as `岗位 JD`, `offer`, `AB 实验`, and `业务方` survived transcription.
- `active_confusion_count`: how many known wrong forms still appear, such as `业务房` or `AV 实验`.

## Product Use

Use each human-corrected sample in three ways:

1. Benchmark candidate STT models and settings.
2. Identify recurring STT failure modes for evaluation and future product decisions.
3. Keep sample-specific terminology as benchmark context, not as a default product hotword library.

Do not blindly productize every confusion pair. Some pairs are context-dependent, especially `自己 -> 字节`.
