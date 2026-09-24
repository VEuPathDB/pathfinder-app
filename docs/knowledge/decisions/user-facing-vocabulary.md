---
type: Decision
title: The user sees studies, searches, strategies and steps, never EDA, WDK, FRAME, BUILD, VERIFY, Lead, sub-agent or Ledger
description: Every string a researcher can read (thread copy, trace verbs and group labels, rail tabs, settings, tool summaries, tool error text a trace row shows, consult questions, error titles) uses the vocabulary below. Internal names stay in code, testids, part kinds, URLs and the dev-mode raw view. Decided 2026-08-30 after the first real session showed "Open in EDA tab", "Search eda studies", "Frame", "Investigation Ledger" and "WDK" on screen.
tags: [decision, copy, frontend, thread, eda, phases]
generated: { by: claude-code/fable-5, at: 2026-08-30T00:00:00Z }
verified: { by: claude-code/fable-5, at: 2026-08-30T00:00:00Z }
status: stable
---

## The rule

A researcher reads about their science and the site they use. PathFinder's
internal architecture (the EDA service, the WDK service, the three phases,
the Lead, sub-agents, the ledger) is not vocabulary they own, so it never
appears in copy. Identifiers (`DS_...`, `ENT_...`, `VAR_...`, WDK step ids)
appear only where the user typed them or where a link needs them.

## The glossary

| Internal | On screen |
|---|---|
| EDA, EDA analysis, EDA tab, EDA workbench | study, the study, Studies (rail tab), "Open study" |
| EDA subset, filter slots | samples, filters |
| EDA compute, differential expression job | comparison, differential expression |
| WDK, WDK strategy, WDK step, WDK count | VEuPathDB (when the site is meant), strategy, step, count |
| FRAME / `frame` | Planning |
| BUILD / `build` / `execution` | Building |
| VERIFY / `verification` | Checking |
| `recover_failed_steps` | Repairing |
| Lead / `lead` | Assistant (only when a label is needed beside other groups) |
| sub-agent | (never shown; the group label is the phase) |
| Investigation Ledger, Ledger | Progress |
| Operational Spec | plan |

## Where it is enforced

- `apps/web/src/lib/models/phaseRoles.ts` holds the one label set and the
  settings descriptions.
- `apps/web/src/features/conversation/toolNames.ts` holds every tool verb; the fallback
  Title-case never produces an internal name because every tool is listed.
- `apps/web/src/vocabulary.test.ts` scans JSX text and string
  literals under `src/features`, `src/app`, `src/lib/components`,
  `src/lib/models` and `src/lib/utils` for the internal words. It carries one
  exception, the stream part kind: every other place an internal name is
  allowed (testid, route, query key, field name) writes it in lowercase, which
  the pattern already passes. The exception's own hits are pinned, so it
  cannot widen unnoticed.
- `apps/api/src/pathfinder/tests/unit/test_user_facing_vocabulary.py` scans
  every `with_summary` line, every `title=`/`detail=` literal of the error
  modules and the study services, every `ModelRetry`/`ToolErrorPayload`
  message and every raised refusal in the study tools and services. It has no
  exceptions: the internal words are matched in the forms only a reader sees.
  It also refuses a summary that interpolates a name ending in `dataset_id`,
  `entity_id`, `variable_id`, `study_id` or `wdk_strategy_id`; a `step_id` is
  the researcher's own step and stays.
- The study modules (`ai/tools/standalone/eda_*.py` and `_eda_*.py`,
  `services/eda/*.py`, `services/strategies/_wdk_step_calls.py`) carry a
  stricter check on every `title=`/`detail=` text, the locals it interpolates
  included: no snake_case name (a tool or a parameter), no `DS_`/`ENT_`/`VAR_`
  /`STUDY_`/`EDAUD_` prefix, and no interpolated name with one of the id
  suffixes above. A refusal that both readers see carries two sentences built
  from the same facts: `detail` for the researcher and `retry` for the model,
  which alone may name a tool or an id (`NoGeneSubsetError`).
- `pathfinder.ai.agents.vocabulary.USER_FACING_VOCABULARY` is the rule's one
  text. The Lead and all three sub-agents append it through
  `with_vocabulary()`, so the digest prose, the spec summary and the result
  summaries the rail renders obey it too; the gate asserts its presence in
  each of the four instruction sets. Recovery runs on the execution agent, so
  four surfaces cover five roles.
- The Lead's instructions tell the model the same rule for its prose and
  its consult questions.

## Rejected

- Keeping "EDA" because VEuPathDB's own UI uses it in places: their users
  see "MapVEu" and study names, not "EDA"; the acronym is the platform team's.
- Renaming the `/eda` route segment now: the URL is not copy, and a route
  rename touches every deep link; it can follow separately.
