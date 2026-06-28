# AI Workflow And Editor Information Refactor Plan

Last updated: 2026-06-28

This document records the planned UI refactor for FluentFlow's Agent workflow page and editor result header. Do not implement these changes until the current version-management work is complete.

## Purpose

The current editor exposes too much generation metadata near the top of the note. Some of that information duplicates the result summary line, some belongs to the Agent workflow explanation, and some is mostly internal debugging detail.

The refactor should make the product easier to read:

- `Agent 工作流` explains what the Agent did, why it did it, and what evidence it used.
- `编辑器` focuses on reading, checking, editing, exporting, and regenerating the note.
- `设置` keeps long-term human preferences and credentials.

## Scope

### In

- Redesign `/processing` as the main Agent workflow explanation page.
- Move useful generation reasoning from the editor into the Agent workflow view.
- Compress the editor title metadata and remove the tall default `AI 生成` panel from the main reading surface.
- Keep advanced technical details available, but behind progressive disclosure.
- Preserve the ability to explain completed results after the fact.

### Out

- No immediate code changes in this planning step.
- No new standalone Agent page.
- No multi-Agent product UI.
- No expansion into interview, meeting, subtitle production, or knowledge-base workflows.
- No decorative Agent theater that is not tied to real task state or real decisions.

## Current Problem

The current editor has two overlapping metadata surfaces:

1. The title summary line shows duration, transcription elapsed time, STT provider/model/speed/language, note mode, segment count, and AI generation status.
2. The `AI 生成` panel shows note mode, prompt template, source language, subtitle mode, summary basis, chunk count, mode reason, and prompt reason.

This creates three issues:

- The editor loses vertical space before the user reaches the actual note.
- The same idea appears twice: how the result was generated.
- User-facing reading is mixed with internal execution details such as model, speed, language auto mode, chunk count, and prompt preset.

## Page Responsibilities

| Page | Should do | Should not do |
| --- | --- | --- |
| 开始处理 | Upload files, start jobs, show queue/progress entry points | Explain detailed Agent reasoning |
| Agent 工作流 | Show what the Agent did, why it chose that path, what evidence it used, and what can be recovered | Ask users to manually tune every runtime parameter |
| 编辑器 | Read notes, check transcript, edit text, regenerate, export, download | Occupy the first viewport with internal generation metadata |
| 设置 | Store credentials, long-term preferences, export connection, and advanced defaults | Explain a specific task's execution story |

## Target Information Architecture

### Agent 工作流

Convert `/processing` from a settings-like page into the primary explainability surface.

Recommended sections:

1. **Current task overview**
   - File name.
   - Job status.
   - Current stage.
   - Completed / failed / waiting state.

2. **Agent execution route**
   - Use a timeline or compact step list:
     - Receive file.
     - Extract or normalize audio.
     - Transcribe with the active STT route.
     - Detect language and material type.
     - Choose note strategy.
     - Generate note.
     - Export to Feishu when enabled.

3. **Agent judgment**
   - Material type: course / lecture when supported.
   - Why this note strategy was selected.
   - Whether the source should preserve original transcript evidence.
   - Whether speaker diarization matters for this material.
   - What the Agent is uncertain about.

4. **Evidence used**
   - Input type.
   - Detected language.
   - Duration.
   - Transcript length.
   - Content structure.
   - Whether the transcript resembles a course or lecture.
   - File name only as a weak signal.

5. **Recovery and next action**
   - If failed: show cause, suggested next step, and available one-click recovery action.
   - If completed: show what can be reviewed in the editor.

6. **Advanced details**
   - Collapsed by default.
   - May include STT provider, model, prompt preset, chunk count, task id, transcription elapsed time, and raw route labels.

### 编辑器

The editor should show only the minimum context needed before the note.

Recommended header metadata:

```text
14:56 · 中文 · 云端转录 · 438 段 · AI 笔记
```

Alternative when the provider label is useful:

```text
14:56 · ElevenLabs 转录 · 课程笔记 · 查看 Agent 工作流
```

The editor should not default-show a large `AI 生成` panel. Replace it with one compact entry:

- `查看 Agent 工作流`
- or `查看生成说明`
- or a small inline status chip that opens the workflow detail.

The transcript and note should become visible earlier in the first viewport.

## Information To Move From Editor To Agent Workflow

Move these out of the editor's default reading surface:

- Note mode reason.
- Prompt preset reason.
- Subtitle mode reason.
- Summary basis.
- Chunk count.
- STT provider/model/speed/language route details.
- Transcription elapsed relative factor.
- Internal prompt template label when it is not user-actionable.

Keep them available in Agent workflow, preferably in clear user-facing language.

## Information To Keep In Editor

Keep only information that helps the user read or act immediately:

- Source title.
- Duration.
- Detected language, if available.
- Broad transcription route: cloud / local, or ElevenLabs when useful.
- Segment count.
- Whether AI note exists, failed, or is still generating.
- A link or button to Agent workflow details.
- Summary failure next step when the note failed.

## Information To Hide By Default

These are useful for debugging or advanced review, but not for the first viewport:

- `medium`.
- `balanced`.
- `auto`.
- Prompt preset names such as `简单版`.
- `分块数: 1`.
- `摘要依据: 原文生成摘要`.
- `字幕模式: 原文字幕`.
- Raw provider route strings.
- Task id.

## Execution Order

1. Redesign the `/processing` page information structure first. Done in first slice: `/processing` is now a read-only Agent workflow explanation surface instead of a settings form.
2. Move editor generation reasoning into the Agent workflow page.
3. Verify that the Agent workflow page can explain a completed result without the editor panel.
4. Replace the editor `AI 生成` panel with a compact workflow/details entry. Done in second slice: the editor now shows a compact generation bar, an Agent workflow link, and collapsed generation details.
5. Compress the editor title metadata into one readable line.
6. Move purely technical metadata into collapsed advanced details.
7. Validate that the transcript and note are visible earlier on desktop and smaller screens.
8. Run frontend build and route tests after implementation.

## Acceptance Criteria

- A user can understand why FluentFlow chose the transcription route and note strategy from `Agent 工作流`.
- The editor no longer repeats the same generation explanation in two large surfaces.
- The editor first viewport prioritizes transcript and note content.
- Technical details remain available without dominating the page.
- The product language matches the current direction: ElevenLabs cloud transcription first, local STT as development/private fallback.
- The implementation does not remove useful failure diagnosis or recovery actions.

## Implementation Notes

- Work in `frontend/src/routes/processing.jsx` before changing `frontend/src/routes/editor.jsx`.
- Reuse existing result fields such as `note_mode_plan_reason`, `prompt_preset_label`, `source_language`, `detected_language`, `stt_provider`, `stt_provider_label`, `stt_model`, `stt_speed`, and segment counts.
- If the existing result object does not contain enough explanation for Agent workflow, add display fallbacks before changing backend schema.
- Keep settings and credentials in `frontend/src/routes/settings.jsx`; do not move credentials into the Agent workflow page.
- Keep copy concise. This is a tool interface, not a marketing page.

## Validation Checklist

- [ ] `/processing` reads as an Agent workflow page, not a settings page.
- [ ] `/editor` shows note content earlier than before.
- [ ] Completed jobs still explain their generation path.
- [ ] Failed jobs still show actionable next steps.
- [ ] No duplicate default display of note mode, prompt reason, and chunk count.
- [ ] `npm run build:frontend` passes.
- [ ] Relevant frontend route tests pass.
- [ ] `git diff --check` passes.
