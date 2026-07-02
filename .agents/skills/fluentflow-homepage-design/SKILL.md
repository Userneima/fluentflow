---
name: fluentflow-homepage-design
description: Use before reviewing, redesigning, or implementing the FluentFlow public homepage, especially `frontend/src/routes/landing.jsx`, hero positioning, homepage copy, visual direction, typography, product mockups, reference comparisons such as Turbo AI, or critiques that the homepage feels generic, heavy, not learning-product-like, or not premium.
---

# FluentFlow Homepage Design

Use this skill as the project-specific homepage design gate. Generic design
skills can improve polish, but this skill defines what FluentFlow's homepage
must become: a modern long-video learning product page, not a dark internal
tool demo or a generic AI feature grid.

When the homepage direction itself is in doubt, use the installed
`huashu-design` skill before production React implementation. Huashu is for
high-fidelity HTML direction exploration, not for editing the app directly.

## Design Read

Read the homepage as:

> Chinese-first learning product for people with many long videos to study.
> FluentFlow generates a high-quality note before watching, so users can learn
> with the video while pausing less and correcting only a few uncertain details.

Borrow from Turbo AI only at the level of product energy:

- direct learning promise;
- light, friendly, fast first impression;
- one clear product moment in the hero;
- generous whitespace and strong hierarchy.

Do not copy Turbo's exact purple brand, fake user counts, broad "learn
anything" scope, logo wall, quiz/flashcard promises, or playful cloud styling.

## Homepage Must Communicate

The first viewport must answer these in order:

1. What problem: long videos are slow to learn when note-taking interrupts
   watching.
2. What FluentFlow does: create structured notes, transcript/subtitles, and key
   visual anchors first.
3. How the user learns: watch the video with prepared notes, then correct a few
   uncertain details.
4. What to do next: start processing a video.

If the first viewport instead explains every capability, model provider, export
route, or internal workflow, simplify it.

## Visual Direction

Prefer light, modern, learning-oriented surfaces.

Good directions:

- study desk, notebook, transcript margin, timeline, highlighted source frame;
- soft but not childish;
- calm product confidence;
- one memorable hero product moment;
- source-grounded reviewability.

Avoid these common failures:

- dark heavy "enterprise dashboard" mood;
- classical serif title that feels like a museum poster or literary magazine;
- stacked dark cards pretending to be a product screenshot;
- warm-neutral cards everywhere with no signature idea;
- three-column feature grids as the main personality;
- generic AI purple/blue gradient;
- fake metrics, fake testimonials, fake school/company logos;
- overpromising flashcards, quizzes, podcasts, or complete understanding.

## Typography Gate

FluentFlow is Chinese-first. Judge Chinese typography first, then English.

Use restrained role separation:

- Display: hero and major section headlines only.
- Body: readable modern sans with generous line height.
- Utility: labels, timestamps, transcript snippets, and data may use tighter
  weight or tabular/mono treatment.
- Controls: never display-scale; keep buttons and nav operational.

Rules:

- Do not use negative letter spacing for CJK titles.
- Do not make "premium" mean old-style serif by default.
- Avoid giant Chinese headlines that need weight alone to feel designed.
- Use line breaks, max width, and `text-wrap` deliberately.
- Mobile must not create awkward single-character or very short orphan lines.

## Hero Product Mock

The hero visual should show one understandable product moment:

- a long video or source at the edge;
- a generated note with structure;
- a transcript/subtitle reference;
- a time or key-frame anchor that proves reviewability.

Keep it simple enough to understand in three seconds. If the mock needs many
cards, badges, and provider labels to explain itself, it is carrying too much.

Provider names such as ElevenLabs, DeepSeek, or Qwen are not hero content unless
the user goal is provider configuration. Move them out of the first impression
or reduce them to non-primary detail.

## Audit Before Editing

Before changing homepage code, state a short audit:

- Current first impression: light learning product, dark tool, generic AI page,
  or something else?
- What is the single hero moment?
- Which visual element is the page's signature?
- Which text is display-scale, and which text must stay operational?
- What existing promise would be misleading if made more prominent?
- What must remain true from
  `docs/superpowers/specs/2026-07-02-fluentflow-long-video-notes-homepage-design.md`?

Then decide whether the work is:

- copy/positioning only;
- visual polish only;
- homepage IA redesign;
- bug fix such as scrolling, dark-mode contrast, or responsive layout.

Do not mix unrelated categories unless Product Intake explicitly combines them.

## Direction Exploration With Huashu

Use this path when the user says the current homepage still feels wrong, compares
it with references such as Turbo AI, or asks for a better design direction.

1. Read `/Users/yuchao/.agents/skills/huashu-design/SKILL.md` if available.
2. Treat this as visual direction exploration, not production implementation.
3. Produce three distinct HTML homepage directions before changing
   `frontend/src/routes/landing.jsx`.
4. Keep all three directions grounded in the same FluentFlow content and real
   capabilities; vary only the design logic.
5. Show screenshots or browser URLs for comparison, then wait for Product Intake
   or the user to choose or combine directions.

Recommended three directions for FluentFlow:

- **Light learning product**: Turbo-like directness, modern Chinese sans,
  friendly surfaces, one clear note-first learning moment.
- **Source-grounded notebook**: transcript margin, video timeline, annotations,
  calm trust, strong reviewability.
- **Focused productivity tool**: less playful, more precise, showing how a long
  video becomes a study asset without becoming a dark dashboard.

Do not ask Product Experience to overwrite the production homepage until one
direction has been selected. The output of this phase should be a decision
artifact, not a checkpoint commit to app code.

## Implementation Boundaries

Likely files:

- `frontend/src/routes/landing.jsx`
- `tests/test_frontend_routes.py`
- `docs/changelog.md` for landed visible changes

Do not change backend, task state, model providers, Agent/MCP contracts,
processing flow, or `frontend/dist`.

Homepage work should also use `fluentflow-frontend-change` and
`fluentflow-git-workflow` when editing code or committing.

If the selected direction comes from Huashu HTML, translate the design into the
existing React/Tailwind stack manually. Do not paste a standalone HTML prototype
into the production route as-is.

## Validation

Required for homepage implementation:

- `git diff --check`
- `npm run build:frontend`
- focused route/source tests when assertions change
- browser verification on desktop and mobile
- light and dark mode screenshots or direct visual observations
- real scroll check from hero to bottom CTA
- verify in the user's already-open browser window when possible. Do not launch
  a temporary Edge/Chrome profile for homepage screenshots unless the user
  explicitly approves it; if automation cannot inspect the current window, give
  the localhost URL and ask the user to view it there.

Do not report a homepage redesign as complete if the page cannot scroll, if the
CTA is unreachable, or if desktop/mobile/dark mode were not actually inspected.
