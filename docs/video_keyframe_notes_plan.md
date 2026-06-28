# Video Keyframe Notes Plan

Last updated: 2026-06-29

This document anchors the plan for adding useful video screenshots to FluentFlow notes. The feature must support both local desktop use and future cloud deployment without tying the product to one runtime path.

## Product Intent

FluentFlow should add screenshots only when they help a course or lecture note. Screenshots are evidence for a specific explanation, slide, formula, UI demonstration, or visual transition. They are not decorative thumbnails and should not turn the editor into a generic video clipping tool.

The system should separate two decisions:

- What moments deserve screenshots: decided by the Agent from transcript, note structure, and later optional visual review.
- How screenshots are produced: decided by runtime capability, such as local FFmpeg, cloud worker, media-provider thumbnails, or disabled fallback.

## Scope

### In

- Course and lecture materials.
- Local FFmpeg extraction for local desktop/private deployments.
- Cloud extraction through a server-side worker that can run FFmpeg.
- Stable result schema for screenshot candidates and generated image artifacts.
- Agent workflow explanation of why screenshots were or were not added.
- Graceful fallback when video file access or FFmpeg is unavailable.

### Out

- Full video editing or clip generation.
- Manual frame-by-frame annotation tools.
- Depending on browser-only canvas capture as the main cloud path.
- Sending all video frames to a model by default.
- Requiring screenshots for every note.

## Recommended Architecture

```text
Task result
-> Agent identifies visual evidence points
-> Runtime chooses extraction provider
-> Provider generates image artifacts
-> Images are attached to note sections
-> Agent workflow explains evidence and fallback
```

Provider types:

| Provider | Runtime | Role |
| --- | --- | --- |
| `local_ffmpeg` | Local desktop / private server | Extract screenshots from local uploaded or downloaded video files. |
| `cloud_ffmpeg_worker` | Aliyun ECS / Docker worker | Extract screenshots on the server and upload or serve artifacts. |
| `media_thumbnail_api` | Mux / Cloudinary style hosted media | Generate thumbnails by timecode when the source is hosted there. |
| `visual_review_grid` | Optional multimodal pass | Build timestamped contact sheets for model review, similar to BiliNote. |
| `disabled` | Any runtime | Preserve note generation and explain why screenshots are unavailable. |

## Execution Plan

### P0: Stabilize Current Frame Artifact Foundation

- [x] Document the local/cloud split and execution order in this file.
- [x] Fix frame artifact writing so nested `frames/*.jpg` files can be persisted and downloaded.
- [x] Normalize frame artifact URLs to `/jobs/{task_id}/artifacts/frame?file={name}`.
- [x] Add tests for nested frame artifacts and URL shape.

### P1: Define Screenshot Result Contract

- [x] Extend `docs/result_schema.md` with `visual_evidence` and `visual_artifacts`.
- [x] Define fields: `timestamp_seconds`, `reason`, `note_section`, `source`, `confidence`, `artifact_kind`, `artifact_url`, `provider`.
- [x] Add compatibility rule: existing `frame_artifacts` are raw candidates, not final note screenshots.
- [x] Expose visual evidence in Agent Task Package without requiring editor UI changes.

### P2: Local Extraction Path

- [x] Refine `backend/core/frame_extractor.py` so extracted frame timestamps are accurate.
- [x] Prefer transcript/note-derived candidate timestamps over blind scene extraction for V1.
- [x] Keep scene extraction as supplemental evidence for slide/video transitions.
- [x] Add a small integration test using a generated short video if FFmpeg is available.

### P3: Cloud Extraction Path

- [ ] Add a provider boundary such as `backend/core/keyframe_provider.py`.
- [ ] Implement `local_ffmpeg` first; make `cloud_ffmpeg_worker` a separate adapter.
- [ ] For Aliyun deployment, run FFmpeg inside ECS/Docker worker and store outputs in OSS or the configured artifact directory.
- [ ] Add environment flags for enabling/disabling screenshot extraction and selecting provider.
- [ ] Update deployment docs with FFmpeg, temp storage, retention, and OSS notes.

### P4: Agent Selection And Note Insertion

- [ ] Let the Agent propose screenshot evidence points after transcript/note planning.
- [ ] Insert screenshots only beside sections where the reason is concrete.
- [ ] Keep model rationale as user-facing evidence summaries, not inner monologue.
- [ ] Add fallback messages when no reliable visual evidence exists.

### P5: Editor And Export UX

- [ ] Show screenshots inline in the note only when attached to a real section.
- [ ] Keep screenshot controls secondary; do not add another large panel.
- [ ] Support Markdown export first, then Feishu image upload, then PDF/Word.
- [ ] Add editor affordance to hide/show visual evidence if screenshots become distracting.

## Risk Rules

- Do not block transcript or note generation because screenshot extraction failed.
- Do not claim a screenshot is semantically important if it was selected only by a timing heuristic.
- Do not expose local filesystem paths in result payloads or exported notes.
- Do not store images indefinitely without following artifact retention rules.
- Do not make the first version depend on a multimodal model; use it as an optional quality upgrade.

## Immediate Next Step

Finish P0 first. The existing code already has a partial frame extraction path, but nested frame artifacts and URLs need to be reliable before building the higher-level screenshot feature.
