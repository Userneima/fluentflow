# FluentFlow Long-Video Notes Homepage Design

Date: 2026-07-02

## Purpose

Redesign the public homepage so FluentFlow no longer reads as a generic video transcription or AI summary tool. The homepage should communicate a specific learning workflow:

> Users have many long videos from different sources that they want to learn from. Watching while taking notes causes constant pausing, rewinding, and manual cleanup. FluentFlow generates a high-quality note first, so users can learn with the video while only correcting a small number of inaccurate note details.

## Product Positioning

Primary positioning:

> FluentFlow turns long videos you want to learn from into high-quality notes before you start studying them.

The video remains the learning source. FluentFlow does not replace watching the video; it reduces the note-taking friction around the video.

Core promise:

- Accept long course, lecture, screen-recording, and video-link materials.
- Generate structured notes, subtitles/transcript, and key visual moments.
- Let users watch the video with a prepared note, correcting only a small number of uncertain details.
- Export or keep the result as a study asset.

## Reference Read

Use these references as direction, not as templates:

- Turbo AI: strong student-facing learning language, study materials, editable notes, and immediate "start studying" energy.
- Mindgrasp: broad AI study system framing with notes, flashcards, quizzes, and student social proof.
- NotebookLM: source-grounded trust and "turn complexity into clarity" framing.
- NoteGPT: direct upload/link tool-entry clarity for video summarization.

FluentFlow should borrow Turbo's learning-first directness and NoteGPT's task-entry clarity, while keeping NotebookLM-like trust around source review. Do not imitate Turbo/Mindgrasp's broad flashcards/quizzes/podcasts promise unless those capabilities actually exist.

## Homepage Narrative

The current homepage is too much like a feature explanation page. The revised homepage should tell this story:

1. I have many long videos I want to learn from.
2. Watching and taking notes at the same time is slow.
3. FluentFlow creates the note, subtitles/transcript, and key visuals first.
4. I watch the video with the prepared note, correcting only the few parts that need human judgment.
5. The result becomes a reusable study asset in FluentFlow, Markdown, PDF, or Feishu.

## Hero Copy

Recommended Chinese hero:

```text
把想学的长视频，先变成高质量笔记
```

Recommended Chinese supporting copy:

```text
把课程、讲座、录屏和视频链接交给 FluentFlow。先得到结构化笔记、字幕和关键画面，再对着视频学习，只改笔记少数不准确的地方。
```

English direction, not final copy:

```text
Turn long videos you want to learn from into high-quality notes first.
Give FluentFlow your courses, lectures, screen recordings, or video links. Get structured notes, subtitles, and key visuals before studying with the video, then fix only the few note details that need your judgment.
```

## Page Structure

### 1. Hero

Goal: Make the use case obvious in the first viewport.

Content:

- H1: high-quality long-video notes.
- Supporting copy: video remains the learning path; FluentFlow reduces pausing and manual note-taking.
- Primary CTA: start processing a video.
- Secondary CTA: view workflow or see example output.
- Visual: a realistic note preview paired with a video timeline or key visual frame, not abstract workflow cards.

### 2. Before / After

Goal: Show the workflow improvement.

Before:

- Open a 1-hour video.
- Pause and rewind repeatedly.
- Write notes manually.
- Clean format afterward.

After:

- Generate note first.
- Watch with prepared notes, subtitles, and key visuals.
- Correct a few uncertain details.
- Save or export.

### 3. What Makes The Note High Quality

Goal: Define "high quality" concretely.

Include only real or landed capabilities:

- Structured chapters and concepts.
- Important examples and reasoning steps.
- Subtitles/transcript retained for review.
- Conservative transcript correction evidence.
- Key visual moments/screenshots when available.
- Exportable Markdown/PDF/Feishu result.

Avoid claims that are not yet true:

- No flashcard, quiz, podcast, or "never miss anything" promise.
- No fake success metrics or social proof.
- No guarantee that all public video links can be downloaded.

### 4. Source Coverage

Goal: Show the many-source scenario.

Sources:

- Course videos.
- Lectures.
- Screen recordings.
- Local video/audio files.
- Subtitle/text files.
- Public video links when supported.

Include honest boundary copy: public video platforms may restrict direct download or captions; local upload is the most reliable route.

### 5. Output / Study Asset

Goal: Show what the user leaves with.

Outputs:

- Structured note.
- Subtitle/transcript.
- Key visuals.
- Processing record.
- Export/download options.

This section should use a product-like visual, ideally derived from real editor/detail surfaces, not generic decorative cards.

## Visual Direction

Reading this as: student/self-learner SaaS landing page with a Turbo-like learning-product language, but grounded in FluentFlow's long-video note quality and reviewability.

Design dials:

- Design variance: 6
- Motion intensity: 4
- Visual density: 4

Constraints:

- Lighter, more learning-oriented than the current dark/heavy tool story.
- Keep trust and clarity; avoid loud gamified student aesthetics.
- Use real product surfaces or realistic generated product composites.
- Do not use generic AI purple/blue gradients.
- Do not make the first screen a text-only manifesto.
- Hero should fit in the first viewport with CTA visible.

## Implementation Boundary

This is a homepage redesign, not a backend or workflow capability change.

Likely files:

- `frontend/src/routes/landing.jsx`
- `tests/test_frontend_routes.py`
- `docs/changelog.md` if the redesigned homepage lands

Possible supporting files only if the executor verifies they are needed:

- shared visual tokens or app route labels under `frontend/src/app/`
- UI docs if a reusable homepage rule is added

Do not change:

- processing flow
- backend APIs
- settings
- Agent/MCP contracts
- generated `frontend/dist`

## Validation

Required for implementation:

- `npm run build:frontend`
- relevant frontend route/static tests
- `git diff --check`
- browser visual verification on desktop and mobile widths
- dark-mode check, because the current homepage recently had dark-mode contrast issues

## Open Design Choices For Implementation

- Whether the hero includes a real upload/link input or a CTA-only path. Recommendation: CTA-only for this iteration unless existing app entry can be safely embedded without duplicating workflow state.
- Whether to show a sample note. Recommendation: show a realistic static sample note panel, not a fake generated result that looks like stored user content.
- Whether to keep "Agent" in the hero. Recommendation: move "Agent" out of the H1 and explain it later as the processing route, because the user goal is learning speed and note quality.
