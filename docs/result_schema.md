# Result, Job, and Agent Task Package Schema

This document is the shared data contract for FluentFlow results. It exists so UI pages, Agent scripts, backend routes, and future generated types do not each invent their own interpretation of a task.

## Design Rules

- The backend stores and returns canonical Result Payload v2 fields.
- The frontend may read legacy aliases, but should normalize them before UI mapping.
- Agent integrations should prefer the Agent Task Package over scraping UI history or ad hoc job fields.
- `raw_segments` and `display_segments` are distinct on purpose; do not collapse them into a single `segments` field.

## Result Payload v2

Every persisted task result should expose:

| Field | Meaning |
| --- | --- |
| `result_schema_version` | Current value is `"2"`. |
| `task_id` | Stable task id when available. |
| `filename` | Machine/source filename, not necessarily user-facing. |
| `raw_title` | Raw title from the source page or file metadata. |
| `display_title` | User-facing title after cleanup. |
| `transcript_text` | Canonical transcript text. |
| `transcript_text_preview` | Short preview for lists and Agent summaries. |
| `raw_segments` | Source-language, editable transcript segments. |
| `display_segments` | Reading/export segments; may include `text_zh` for bilingual subtitles. |
| `summary_markdown` | AI note content in Markdown. |
| `summary_status` | `completed`, `failed`, `skipped`, or `pending`. |
| `summary_error` | Failure reason when note generation fails. |
| `summary_skipped` | True when the task intentionally skipped AI notes. |
| `source_language` | Language used for transcript/note decisions. |
| `detected_language` | Language detected by STT or post-processing. |
| `subtitle_mode` | Example values: `source_only`, `bilingual_zh`. |
| `translation_status` | Translation state for bilingual subtitles. |
| `artifacts` | Downloadable outputs keyed by artifact kind. |
| `visual_evidence` | Optional Agent-selected screenshot evidence points for note sections. These are final note-level decisions, not raw frame candidates. |
| `visual_artifacts` | Optional generated image artifacts attached to `visual_evidence`. |
| `frame_artifacts` | Legacy/raw candidate frame artifacts. These may exist when the runtime extracted frames for multimodal review, but they are not final note screenshots unless promoted into `visual_evidence`. |
| `requested_note_mode` | User-requested note mode. |
| `resolved_note_mode` | Actual note mode used after planning/fallback. |
| `prompt_preset` / `prompt_preset_label` | Prompt template metadata. |
| `note_mode_*` | Current note-planning and coverage metadata. These remain compatible until folded into the broader Processing Plan. |
| `chapter_coverage` | Optional Chapter Coverage Evidence Table v1 for `chapter_coverage` notes. |
| `processing_plan` | Processing Plan v1. Explains the automatic Agent route used for this result. |

Segment shape:

| Field | Meaning |
| --- | --- |
| `text` | Segment text. In `raw_segments`, this is the source-language transcript. |
| `text_zh` | Optional Chinese translation on `display_segments`. |
| `start` / `end` | Seconds from media start. |
| `speaker` | Optional speaker label. |
| `source_start_index` / `source_end_index` | Optional mapping back to raw segments after sentence merging. |

Legacy aliases are read-only compatibility inputs:

| Legacy field | Canonical replacement |
| --- | --- |
| `segments` | `raw_segments` |
| `cleaned_segments` | `raw_segments` when no stronger source exists |
| `bilingual_segments` | `display_segments` |
| `translated_segments_zh` | Merged into `display_segments[].text_zh` |

## Job Payload

## Processing Plan v1

`processing_plan` explains the task route FluentFlow chose. The first version is deterministic and evidence-based; it should not claim deep semantic understanding of content quality.

| Field | Meaning |
| --- | --- |
| `processing_plan_version` | Current value is `"1"`. |
| `generated_by` | Usually `deterministic_runtime_plan`. |
| `execution_mode` | Current value is `automatic`; users are not asked to approve before execution. |
| `requires_user_confirmation` | Current value is `false`. |
| `planning_stage` | `initial` when the plan is generated before transcript content exists; `completed` after transcript content can be used. |
| `goal.primary` | First version only uses `course_notes` or `lecture_notes`. Tutorial, interview, translation, and knowledge-base goals are out of scope for v1. |
| `goal.reason` | Short explanation of why that goal is used. |
| `material.type` | Route-level material type, such as `course_transcript_file`, `course_material`, `lecture_material`, `course_video_pending_content`, or `lecture_video_pending_content`. |
| `material.confidence` | `high`, `medium`, or `low`; low confidence means the route is inferred from metadata only. |
| `material.evidence` | Source facts used by the planner, such as transcript content markers, `source_type=video_link`, or `duration>=30min`. |
| `material.evidence_policy` | Declares evidence weights. Transcript content is primary once available; filename is always weak. |
| `execution.scope` | `local`, `cloud`, or `unknown`. |
| `execution.transcription_tool` | Tool family, such as `local_whisper`, `cloud_stt`, or `transcript_parser`. |
| `steps` | Ordered execution steps with `id`, `label`, `tool`, and `reason`. |
| `note_strategy` | Folded note planning fields: requested, selected, resolved mode, reason, confidence, warnings, fallback, provider, and model. |
| `expected_outputs` | Expected artifacts such as transcript, subtitles, bilingual subtitles, Markdown note, and downloads. |
| `risk_notes` | Honest limitations or fallback notes for the plan. |

Compatibility rule: keep legacy `note_mode_plan_*` fields on the Result Payload, but new UI and Agent surfaces should prefer `processing_plan.note_strategy`.

## Chapter Coverage Evidence Table v1

`chapter_coverage` is the reviewable evidence table behind a `chapter_coverage` note. It productizes the intermediate evidence extraction and chapter planning output so users and Agents can inspect why a note section exists and which source evidence it used.

Top-level shape:

| Field | Meaning |
| --- | --- |
| `chapter_coverage_version` | Current value is `"1"`. |
| `summary` | Counts for segments, evidence, chapters, important evidence, coverage checks, and revision usage. |
| `segments` | Stable source text chunks used for evidence extraction. Records character ranges and, when timestamped subtitles exist, `start_seconds` / `end_seconds`. |
| `evidence` | Evidence rows with id, order, type, importance, text, keywords, quote, source chunk ids, coverage status, bound chapter ids, and optional time range. |
| `chapters` | Planned note chapters with id, order, title, purpose, source chunk ids, evidence ids, and optional time range. |
| `missing_important_evidence_ids` | Important evidence not assigned to a chapter before any final coverage revision. |

The legacy count fields (`note_mode_evidence_count`, `note_mode_chapter_count`, `note_mode_important_evidence_count`, `note_mode_covered_important_evidence_count`, `note_mode_coverage_missing_count`) remain as list/stat shortcuts. They must match the `chapter_coverage.summary` values when `chapter_coverage` is present.

Time binding is deterministic. The backend maps `char_start` / `char_end` to existing `raw_segments` or `display_segments`; it must not ask a model to invent timestamps. If no reliable timestamped segments exist, time fields are omitted and the UI should fall back to character ranges or source chunk ids.

Agents should read `note.chapter_coverage` from the Agent Task Package. Task detail pages may also expose `chapter_coverage` at the top level for UI rendering.

## Note Quality Evaluation Report v1

`scripts/evaluate_note_quality.py` generates offline evaluation reports from Result Payload v2 or Job Payload JSON files. These reports are for product calibration and should not be written back into normal user task results.

Top-level collection:

| Field | Meaning |
| --- | --- |
| `note_quality_collection_version` | Current value is `"1"`. |
| `run_count` | Number of evaluated result files. |
| `modes` | Aggregate counts and compression metrics grouped by `resolved_note_mode`. |
| `reports` | Per-run quality report list. |

Per-run report:

| Field | Meaning |
| --- | --- |
| `note_quality_report_version` | Current value is `"1"`. |
| `sample` | Sample id, title, source path, source type, and duration. |
| `run` | Requested/resolved note mode, prompt preset, provider/model, and note status. |
| `material_metrics` | Transcript length, segment counts, language, and subtitle mode. |
| `note_metrics` | Summary length, sentence count, and compression ratio. |
| `coverage_metadata` | Recorded chapter coverage metadata already present on the result. |
| `usage_metrics` | Elapsed seconds, model calls, token usage, and units when available. |
| `quality_review` | Optional human/model review payload. Missing review means `pending_review`; scripts must not invent quality scores from text length. |
| `observable_warnings` | Mechanical warnings such as missing summary or missing coverage metadata. These are review prompts, not final quality judgments. |

## Visual Evidence v1

Visual evidence is the result contract for screenshots that help explain a specific course or lecture note section. It should be generated only when the system can name why a frame helps the user.

`visual_evidence` is an ordered list:

| Field | Meaning |
| --- | --- |
| `id` | Stable evidence id within the task, such as `visual_001`. |
| `timestamp_seconds` | Seconds from media start. |
| `reason` | User-facing explanation of why this screenshot matters. Do not expose model inner monologue. |
| `note_section` | Optional note heading or section id this screenshot supports. |
| `source` | Selection source, such as `agent_transcript`, `scene_change`, `manual`, or `visual_review_grid`. |
| `confidence` | `high`, `medium`, or `low`. Low confidence screenshots should not be inserted by default. |
| `provider` | Extraction provider, such as `local_ffmpeg`, `cloud_ffmpeg_worker`, `media_thumbnail_api`, or `disabled`. |
| `artifact_kind` | Artifact key when a generated image exists. |
| `artifact_url` | Downloadable or embeddable image URL. Must not expose local filesystem paths. |

`visual_artifacts` is a keyed object for image outputs. Each value follows the same artifact shape as `artifacts` and may add:

| Field | Meaning |
| --- | --- |
| `timestamp_seconds` | Source media timestamp used to generate the image. |
| `content_type` | Usually `image/jpeg` or `image/png`. |
| `provider` | Runtime provider that generated the artifact. |

Raw `frame_artifacts` are compatibility/candidate outputs. They may be exposed for diagnostics or future visual review, but UI should not present them as final note screenshots unless `visual_evidence` promotes them with a concrete reason and section association.

Final note screenshots must pass the visual evidence policy before they are shown or exported:

- Use screenshots as evidence for a specific note section or knowledge point, not as decoration.
- Prefer frames that contain definitions, processes, formulas, code, charts, tables, key comparisons, product interfaces, or concrete demonstrations.
- Exclude low-value frames such as covers, tables of contents, pure title pages, thanks/end pages, transition frames, pure talking-head shots, subtitle-only frames, black/white frames, and irrelevant images.
- Apply global density control: short notes should usually contain only one or two screenshots, long notes still cap at a small number of high-value images, and repeated/near-duplicate frames should only appear once.
- Every promoted screenshot should keep `timestamp_seconds` so the UI can use it as a review anchor and jump back to the original video when playback is available.
- If an Agent-generated Markdown image reference does not pass the policy, remove that image reference from `summary_markdown`; do not leave unpromoted screenshots in the note body.

V1 planning is intentionally two-stage:

- Initial plan: generated at task creation from input type, selected execution route, local/cloud capability, and weak filename hints.
- Completed plan: generated or refreshed after transcription from transcript language, length, duration, and content structure. If transcript content conflicts with filename hints, transcript content wins.

The Job Payload wraps a result with task execution metadata:

| Field | Meaning |
| --- | --- |
| `task_id` | Stable task id. |
| `status` | Backend status such as `queued`, `running`, `completed`, `failed`, or `cancelled`. |
| `task_state` | Frontend-normalized state: `idle`, `uploading`, `queued`, `running`, `completed`, `failed`, `cancelled`, or `cached_only`. |
| `stage` | Current processing stage. |
| `progress` | Numeric progress percentage when measurable. |
| `source_type` / `source_filename` | Source metadata. |
| `summary_status` | Job-level note state mirror for list rendering. |
| `metadata` | Worker/runtime metadata. |
| `result` | Result Payload v2. |

Video-link jobs may include `metadata.asset_strategy`:

| Field | Meaning |
| --- | --- |
| `transcript_asset` | How the note input was or will be obtained, such as YouTube captions or STT from media. |
| `playback_asset` | Playback availability: `playback_mode` may be `local_file`, `embedded_url`, `external_url`, or `unavailable`. |
| `visual_asset` | Whether local video is available for screenshots/visual evidence. |
| `download_status` | Video download state, such as `skipped`, `pending`, `running`, `completed`, `slow`, or `failed`. |
| `failure_reason` | Stable machine reason when download/caption preparation fails, such as `timeout`, `forbidden`, `rate_limited`, `too_large`, `no_captions`, or `unknown`. |

For YouTube links, the note path may complete from captions while playback falls back to `external_url`. UI and Agent surfaces should not treat a missing local video file as a failed note task.

`cached_only` is a frontend state, not a backend persistence state. It means the browser has enough cached result data to open a task even when the backend task row is unavailable.

## Agent Task Package v1

Agents should use `GET /agent/v1/tasks/{task_id}/package` as the stable read model.

Top-level shape:

| Field | Meaning |
| --- | --- |
| `agent_task_package_version` | Current value is `"1"`. |
| `task` | Task id, status, stage, progress, and timestamps. |
| `title` | User-facing task title. |
| `source` | Source type, filename, title, URL, duration, and file size. |
| `transcript` | Transcript availability, text, preview, raw/display segments, language, subtitle and translation state. |
| `note` | Note status, Markdown, diagnosis, modes, prompt metadata, and generation stats. |
| `artifacts` | Download/export outputs by kind, with URL and optional local path. |
| `visual` | Optional visual evidence package with final screenshot evidence and generated image artifacts. |
| `usage` | Estimated and billable processing units. |
| `next_actions` | Agent-callable follow-up actions, such as `wait` or `regenerate_note`. |
| `processing_plan` | Same Processing Plan v1 object exposed on the result, generated on read for old tasks when missing. |

`note.diagnosis` explains failure or missing-note cases with:

| Field | Meaning |
| --- | --- |
| `status` | `completed`, `pending`, `skipped`, `failed`, or `unavailable`. |
| `code` | Stable machine-readable reason, such as `transcript_only_mode`, `quota_insufficient`, or `job_scope_mismatch`. |
| `severity` | UI/Agent severity. |
| `title` / `detail` | Human-readable explanation. |
| `next_action` | Suggested recovery action. |
| `retryable` | Whether retry/regenerate is meaningful. |

## Frontend Runtime Normalization

Frontend code should normalize external payloads through `frontend/src/lib/resultSchema.js` before mapping them into history entries, current jobs, editor state, or Agent displays.

The normalizer:

- Converts legacy segment aliases into `raw_segments` and `display_segments`.
- Derives `summary_status` when older payloads only have summary content, skip flags, or errors.
- Adds `task_state` to job payloads using `frontend/src/lib/taskState.js`.
- Keeps legacy fields on the object for compatibility, but callers should read canonical fields.

## Non-Goals

- This document does not define database migrations.
- It does not require old browser history to be rewritten eagerly.
- It does not define future multi-agent planning beyond Processing Plan v1.
