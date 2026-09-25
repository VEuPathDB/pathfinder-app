---
type: Convention
title: One name per concept
description: The lexicon scripts/check-vocabulary.mjs reads. One row per concept a researcher or the model reads about, its one name, the synonyms it bans and where the ban applies; then the exemptions, the raw values that never reach copy, and the pairs of names that are two concepts and both stay.
tags: [copy, vocabulary, frontend, agents, gates]
generated: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
status: stable
---

The rule and the rejected alternative are in
[one name per concept](../decisions/one-name-per-concept.md). This page is the
data the gate reads: `node scripts/check-vocabulary.mjs` fails when a banned
synonym appears in a string a reader of its scope sees.

The scope is `researcher` or `all`. A `researcher` row reads the web app's copy
(JSX text, the `label`, `title`, `aria-label`, `placeholder`, `description`
slots, `toast` arguments and every prose literal), the `detail=` and `title=`
texts under `apps/api/src/pathfinder/transport` and `services`, and the tool
summaries (`with_summary`) a trace row shows. An `all` row also reads the
model's text: every prose string under `apps/api/src/pathfinder/ai` and
`assistants`, the docstring of every function a toolset registers, and the
prompt templates. Identifiers, imports, paths, test ids, log lines and tests are
never read.

# The lexicon

| Concept | Name | Banned synonyms | Scope | Reason |
|---|---|---|---|---|
| What the assistant keeps while it works in one conversation, shown in the rail | notes | scratchpad, notebook | all | The tools already say note, list notes and pin note; a second word for the same list makes two features out of one. The runtime package keeps its module name `assistant_core.scratchpad`. |
| The researcher's free text on an answer or an offer | comment | add a note, researcher's note | all | "Note" is the notes panel's word, and this text is not a note the assistant keeps. |
| A memory about a saved gene set, one kind of memory | gene set memory | gene set note | all | Notes belong to one conversation and memories to every conversation; a memory kind called "notes" joins the two. |
| One exchange between the researcher and the assistant | conversation | chat, thread, future session | all | The sidebar, the route and the API say conversation; thread is the runtime's word. |
| One VEuPathDB site, such as PlasmoDB | site | database | all | The site menu, every route and the availability refusal say site. |
| A VEuPathDB search strategy | strategy | pipeline, search tree, graph, plan AST, invalid plan | researcher | VEuPathDB's word; graph is the canvas code's word, and plan is the operational spec, which is a different thing. |
| One step of a strategy | step | node, leaf | researcher | VEuPathDB's word. The model's structure tools take `leaf` and node kinds, so the model's text keeps them. |
| One search of the plan, before it is a step | search | criterion, criteria | researcher | The plan is shown as a plan of searches; criterion is the model's word for it. |
| What the assistant does after a build to test it | check | verification, verify | researcher | The glossary shows the phase as Checking. |
| A piece of work that runs in the background | task | job | researcher | The Tasks panel lists every one. |
| A study computation, such as differential expression | comparison | compute | researcher | The glossary in [the user-facing vocabulary](../decisions/user-facing-vocabulary.md). |
| The analysis the assistant runs on a study | study | analysis workflow | researcher | The glossary in [the user-facing vocabulary](../decisions/user-facing-vocabulary.md). |
| A strategy's run against saved control sets | scored run | scored experiment | all | Experiment names a site's experiment card; the settings already call these runs. |
| What a step returns | results | result set | all | VEuPathDB shows a step's results. |
| A saved set of genes PathFinder holds | gene set | gene list | all | The API, the table and every panel say gene set. |
| The person using PathFinder | researcher | user | researcher | Copy addresses them as "you" and names them researcher. |
| A question the assistant asks before it builds | question | consult | researcher | Consult is the tool's name. |
| The assistant the researcher talks to | assistant | agent | researcher | The composer, the empty states and the assistant menu say assistant; agent is the code's word. |
| The models a conversation runs on, set in the Model tab of Settings | model | engine, orchestrator | researcher | The Settings tab is called Model; no tab is called AI Engine, and orchestrator is the code's word for the Lead. |
| A site PathFinder cannot reach now | couldn't reach | not responding | researcher | The site menu, the rail trigger and the notice say "Couldn't reach" and the site's short name. |
| A conversation the researcher deleted, restorable from the sidebar | recently deleted | dismissed | researcher | The sidebar's list is called Recently deleted; dismissed is the column's name in the code. |

# Exemptions

| Synonym | Path | Reason |
|---|---|---|
| thread | apps/web/src/lib/telemetry/globalHandlers.ts | The browser's main thread, in a telemetry event no researcher reads. |
| user | apps/web/src/features/conversation/content/parts/PublishToVdiButton.tsx | "User dataset" is VEuPathDB's own name for an upload. |
| chat | apps/web/src/features/conversation/runtime/buildRequestBody.ts | A developer invariant that names the chat request body builder. |
| chat | apps/web/src/features/conversation/runtime/chatHelpersContext.ts | A developer invariant that names the chat runtime hook. |
| chat | apps/api/src/pathfinder/ai/conversation/_turn_helpers.py | An internal `ValueError` that names the chat request's site field. |
| not responding | apps/web/src/app/components/BusyWorkerBanner.tsx | The background service that runs a turn, not a site. |

# Raw values

A raw value is an identifier that holds an id, not a name. The gate fails when a
template or a JSX expression puts one into the web app's copy, by its name or as a
property (`data.siteId`). This table reads the web app only.

| Identifier | Name | Reason |
|---|---|---|
| `siteId` | `siteShortName(siteId)` | A site's id is `plasmodb`; a researcher reads the site as PlasmoDB. The long form, PlasmoDB (Plasmodium), names a site only in the site menu, where the organism tells the sites apart. |

# Two names, two concepts

These pairs look like synonyms and are not. Both names stay, and the gate bans
neither.

| Names | Why both stay |
|---|---|
| notes, memory | Notes belong to one conversation; a memory reaches every conversation. |
| plan, strategy | The plan is what the assistant will build; the strategy is what VEuPathDB holds. |
| dataset, study, experiment | A dataset is a researcher's upload, a study is a study on the site, an experiment is a site's experiment card. |
| gene set, control set | A control set is a set of known genes a check scores a strategy against. |
| check, evidence | A check is the act; the evidence card is what it leaves in the conversation. |
| rail, sidebar | The rail is on the right of a conversation; the sidebar lists the conversations. |
| approve, confirm | Approve answers a tool that asks first; confirm answers a dialog about a deletion. |
| pin (a note), pin (a memory) | Both keep an item in front of the assistant; the item says which. |
