# FluentFlow Next Execution Plan

Last updated: 2026-06-28

This document is the short execution anchor for the next stage of FluentFlow. If a future task conflicts with this document, prioritize the path below unless the product direction has explicitly changed.

## Core Focus

FluentFlow's next stage should focus on one product story:

> Turn course and lecture audio/video into reliable, editable, exportable learning notes through a visible Agent workflow.

The product should not drift into a generic STT tool, a full knowledge base, a subtitle production suite, or a multi-Agent demo. The first credible version is a narrow but complete learning-material workflow.

## Scope

### In

- Course and lecture notes as the first target material type.
- ElevenLabs Scribe as the default cloud STT path for public product and demo use.
- Local faster-whisper as development, private-use, and fallback capability.
- Agent workflow visibility: plan, judgment basis, tool trace, failure diagnosis, and recovery actions.
- Editor reliability: transcript, note, regeneration, export, and task history should remain usable after long tasks.

### Out

- Azure as the future default STT route.
- Multi-Agent product UI.
- Interview, meeting, subtitle translation, and knowledge-base workflows as first-class product goals.
- SaaS-grade billing, organization management, or enterprise permission systems.
- Cosmetic Agent theater that does not expose real decisions or real tool execution.

## Execution Order

### P0: Stabilize The Current Mainline

- [ ] Commit the current sidebar and terminology cleanup so `Agent 工作流` fully replaces the old `处理设置` meaning in the UI.
- [ ] Run the normal frontend validation after that cleanup: `npm run build:frontend` and `git diff --check`.
- [ ] Check that no secret, runtime artifact, local media file, database, or private doc is staged.

### P1: Make ElevenLabs The Real Cloud STT Default

- [x] Verify `/process`, queue processing, retranscription, and task recovery all use `elevenlabs_scribe` when cloud STT is selected.
- [x] Make deployment readiness checks report ElevenLabs configuration clearly, especially missing `ELEVENLABS_API_KEY`, quota/credit problems, and provider mismatch.
- [x] Keep Azure only as legacy compatibility code and documentation history, not as the product's future default path.
- [ ] Smoke test with a short course or lecture file: upload, transcribe, generate note, reopen task, download transcript, and export when Lark is configured.

### P2: Turn Agent Workflow Into The Product Surface

- [x] Convert `/processing` from a parameter panel into an Agent workflow view: current/recent task, execution route, selected route, judgment basis, evidence, next action, and collapsed advanced details.
- [ ] Move human-maintained long-term preferences to `Settings`; remove or hide choices that the Agent now decides automatically.
- [ ] Show the same Agent plan and tool trace in task detail/editor so completed jobs explain what happened after the fact. First slice is done: editor AI summary footer now links to Agent workflow and hides detailed generation reasons behind disclosure.
- [ ] Make failure states actionable: show diagnosis, next step, and one-click recovery where the system already knows the correct action.

### P3: Protect The Course/Lecture Note Quality Loop

- [ ] Evaluate several real course and lecture materials with the current note strategy.
- [ ] Record where notes fail: missed concepts, bad hierarchy, over-summary, hallucinated structure, weak examples, or poor bilingual handling.
- [ ] Improve prompts and chunking only from real failure cases, not from abstract prompt tweaking.
- [ ] Keep the distinction clear between STT quality, transcript cleanup quality, and note-generation quality.

### P4: Clean Up Product And Public Docs

- [ ] Update `docs/product_overview.md`, `docs/usage_guide_cn.md`, `docs/ops_runbook.md`, deployment docs, and public introduction docs so they describe ElevenLabs + Agent workflow as the current direction.
- [ ] Preserve historical Azure mentions only where they explain legacy behavior or changelog history.
- [ ] Keep `docs/agent_execution_plan.md` as the detailed roadmap; use this document as the short priority anchor.
- [ ] Avoid adding new planning documents unless they replace or clearly specialize an existing one.

## Decision Rules

- If a feature does not improve the course/lecture-to-learning-note path, defer it.
- If a UI control exists only because the old tool required manual setup, move it to Settings or remove it.
- If Agent output cannot be tied to real input, real state, or real tool execution, do not surface it as intelligence.
- If a task helps the interview story but weakens real user completion, prioritize real completion.
- If a refactor does not reduce current failure modes or make the Agent workflow easier to maintain, postpone it.

## Validation Checklist

Before treating this stage as done:

- [ ] A fresh user can upload a short course/lecture file and reach a usable note without understanding STT provider details.
- [ ] The user can see why the Agent chose the route and strategy it chose.
- [ ] A failed task gives a clear reason and a realistic next action.
- [ ] Completed tasks can be reopened from history with transcript, note, plan, and artifacts intact.
- [ ] The public product story no longer depends on Azure subscription readiness.
- [ ] Documentation, UI terminology, and backend defaults all point in the same direction.
