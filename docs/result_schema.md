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
