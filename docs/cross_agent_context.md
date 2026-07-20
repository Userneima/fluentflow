# FluentFlow Cross-Agent Product Context

Last updated: 2026-07-20

This is the shared orientation and decision-routing document for every
FluentFlow agent, human maintainer, and execution thread. Its purpose is to
keep multiple conversations working from the same product model without
turning this file into a duplicate architecture, deployment, or progress log.

Read this document at the start of a new execution or handoff, then read the
domain documents it points to. Do not copy a stale chat summary into a task
brief as if it were product truth.

## 1. What Counts As Current Truth

When sources disagree, use this order and record the discrepancy instead of
silently choosing the most convenient one:

1. The user's latest explicit product decision in the main conversation.
2. A reviewed decision in the current product contract or roadmap.
3. Current source code, schema, and committed tests for implemented behavior.
4. Verified runtime evidence for deployed behavior: process configuration,
   database, logs, API response, or a real user-path check.
5. Current product and operations documents.
6. Private handoffs, old plans, screenshots, and chat summaries.

The following are different facts and must never be conflated:

| Fact | How to verify it |
| --- | --- |
| Local code is implemented | `git log`, source, and relevant tests |
| Code is on the shared remote | branch/upstream comparison or remote PR |
| Code is deployed | deployment revision plus runtime health/version evidence |
| A workflow works for a user | real end-to-end check with the relevant account and data |

Private handoffs may contain useful working context, but they are not a public
source of truth and must not be copied into public docs with credentials,
production addresses, personal data, or user content.

## 2. Stable Product Model

FluentFlow turns long video, audio, links, and subtitle material into editable,
reviewable learning notes. The primary value is not generic transcription: it
reduces the work between a long learning material and a usable note that can be
reviewed, corrected, downloaded, or exported to Feishu.

The core user path is:

```text
Import material -> process with visible task state -> review transcript and note
-> correct or regenerate -> download or export
```

Do not expand a task beyond this path unless a product decision explicitly
changes the product boundary. FluentFlow is not currently a full collaborative
knowledge base, video editor, subtitle-production tool, or organization billing
product.

## 3. Non-Negotiable Product Decisions

These decisions are shared constraints for UI, backend, Agent API, MCP, and
operations work. The detailed contracts remain the authoritative references.

| Decision | Meaning | Authority |
| --- | --- | --- |
| Account owns portable results; device owns original media | Cloud may hold task state, transcript, notes, and lightweight outputs. A desktop source video remains local unless the user explicitly uploads it for cross-device playback. | `docs/hybrid_execution_sync_contract.md` |
| Execution location is not STT provider | `local_desktop`, `cloud`, and future `connected_desktop` describe where work runs; they are not aliases for Whisper or ElevenLabs. | `docs/hybrid_execution_sync_contract.md` |
| Web cannot silently use local machine capabilities | A browser on the hosted domain cannot read local files, run FFmpeg, or run a local STT model without an explicit desktop connection and user confirmation. | `docs/hybrid_saas_execution_roadmap.md` |
| Default cloud retention is limited | Cloud task results and optional OSS original media have a 7-day product retention policy. Account deletion has a 7-day cancellation window before cloud data is permanently removed. | `docs/hybrid_saas_execution_roadmap.md` |
| Raw transcript is evidence, not disposable draft text | Model-assisted corrections must not overwrite raw STT fields. Corrections must remain inspectable and notes must disclose their input source. | `docs/result_schema.md` |
| Agent/MCP are product surfaces, not a side channel | A task workflow that an external agent can submit, inspect, retry, export, or diagnose must preserve documented Agent API and MCP parity. | `docs/agent_mcp_parity.md` |
| Feishu product export belongs to the user | The standard multi-user path is User OAuth. It exports to the current user's personal library by default; an explicit folder token remains a compatibility route. Local `lark-cli` and tenant-token routes are maintenance/private-deployment compatibility paths. | `docs/operations_runbook.md` |

## 4. Current Shared Baseline

This is a product-status baseline, not deployment proof. Verify the runtime
before claiming any item is live.

- The desktop-to-cloud result-sync contract exists. The completed scope covers
  desktop device credentials, idempotent result/state synchronization, offline
  outbox retry, sync status UI, and cross-device read-only result access.
- The default first-version boundary is desktop local STT plus cloud result
  synchronization. Hosted-web cloud transcription remains a separate cloud
  route; it does not gain local STT merely because the same user owns a desktop
  device.
- Original video playback is local to the processing device unless the user
  explicitly chooses the optional OSS cross-device route.
- User OAuth Feishu export uses the user's own identity. Current source behavior
  defaults to creating a document at the root of that user's "My Library";
  enabling or changing Feishu permissions requires app publication and user
  reauthorization before it is available in a deployed environment.
- The current repository may be ahead of the shared remote or deployment. Every
  release/deployment task must establish that state anew; never infer it from
  this document.

## 5. Required Reading By Work Type

| Work type | Read before changing anything |
| --- | --- |
| Any cross-thread or new execution task | This document, `docs/context_index.md`, `docs/agent_task_brief.md` |
| UI, navigation, page ownership, dialogs, responsive behavior | `docs/ui_design_system.md`, `docs/workflow_design_system.md` |
| Task state, persistence, results, retention, sync, account access | `docs/result_schema.md`, `docs/hybrid_execution_sync_contract.md`, `docs/account_user_access_model.md` when account semantics change |
| Agent API, MCP, Agent task package | `docs/agent_mcp_parity.md`, `docs/mcp_integration.md` |
| Upload, processing, providers, video links, media retention | `docs/operations_runbook.md` and the relevant capability plan or skill |
| Deployment, environment, backup, cleanup, rollback | `docs/operations_runbook.md`, `deploy/README.md` |
| Public homepage | `.agents/skills/fluentflow-homepage-design/SKILL.md` and the Homepage Experience handoff |

## 6. Shared Execution Protocol

Before a non-trivial change, the owning agent must state:

1. The user goal, not just the requested mechanism.
2. The relevant source-of-truth documents and any known disagreement.
3. In-scope and out-of-scope surfaces.
4. Whether UI confirmation, Agent/MCP parity, schema compatibility, changelog,
   or deployment verification is required.
5. The smallest validation path that proves the requested outcome.

One work unit has one outcome. Do not combine visual polish, queue semantics,
OAuth changes, and deployment cleanup merely because they appear in the same
conversation. Split by user workflow and risk boundary.

For an execution handoff, use the task brief template in
`docs/agent_task_brief.md`. Treat its proposed files and hypotheses as
provisional until the executor checks the current repository.

## 7. Completion And Memory Update

At the end of a work unit, report:

- changed files and commit hash;
- validation actually run;
- whether the behavior is only local, on the remote, or deployed and verified;
- intentionally untouched work and remaining risk;
- any durable decision that must be recorded.

Update the narrowest appropriate document when the work changes a durable
decision:

| Change | Update location |
| --- | --- |
| Product scope, retention, login, data ownership, SaaS boundary | `docs/hybrid_saas_execution_roadmap.md` or the relevant contract |
| Data/result field meaning | `docs/result_schema.md` and compatibility tests |
| Agent/MCP capability or parity | `docs/agent_mcp_parity.md` and related tests |
| Runtime/deployment/recovery procedure | `docs/operations_runbook.md` or `deploy/README.md` |
| User-visible product behavior | `docs/changelog.md` under `Unreleased` |
| Conversation routing or agent responsibilities | private handoff / thread-routing documents |

Do not update this document for ordinary code changes. Update it only when the
shared product model, truth hierarchy, or cross-agent operating rule changes.

## 8. What This Document Does Not Do

- It does not replace actual code, tests, or runtime verification.
- It does not record secrets, production hostnames, account data, or task
  contents.
- It does not make a local commit equivalent to a release.
- It does not authorize a new product direction. The main product conversation
  still makes those decisions.
