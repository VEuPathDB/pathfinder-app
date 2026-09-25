---
type: Reference
title: UAT known limits
description: What UAT does not count as a bug, because it is decided or already on the backlog - each with the flow where a runner meets it and how it shows.
tags: [uat, known-limits, decisions, backlog]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# Known limits

A runner who meets one of these records the flow as `pass` (or `blocked` where noted) and does not file a bug. A behaviour that goes beyond the row (a wrong count, a crash, another sentence) is a bug.

## Decided behaviour

| Behaviour at UAT | Flow | Decided in |
|---|---|---|
| The study tab is read-only: no subset editor, no comparison form, no threshold controls. The subset, the comparison and the cut are edited on the site through `Open in <Site>` | E1, E3, E5 | [PathFinder shows what the AI did, and the site edits](../decisions/pathfinder-shows-what-the-ai-did-and-the-site-edits.md) |
| A dataset is uploaded on the site's My Data Sets page (`Upload on VEuPathDB`), never through PathFinder; PathFinder never deletes a dataset | E6, G3 | [A private dataset is uploaded on the site and analysed here](../decisions/a-private-dataset-is-uploaded-on-the-site-and-analysed-here.md) |
| Publishing a gene set is a button a person presses, never something the assistant does; a published dataset is not a search input | G3 | [VDI is a publish target, not a store](../decisions/vdi-is-a-publish-target-not-a-store.md) |
| Enrichment is not run in PathFinder; the evidence card links `Run GO, pathway or word enrichment in <Site>` | V1, G2 | [VERIFY shows its evidence](../decisions/verify-shows-its-evidence.md) |
| Another site's experiment appears as a labelled line (`experiments on <site>`) and is never bound | N9, X2 | [Another site's experiment informs a criterion and never binds](../decisions/another-site-informs-and-never-binds.md) |
| A down site is refused on its own routes with `Couldn't reach <site>`; the other sites work | F3, R1 | [A site that is down is down on its own](../decisions/a-site-that-is-down-is-down-on-its-own.md) |
| Every WDK-backed feature needs a registered VEuPathDB login; a guest is refused | F1 | [A WDK-backed feature requires a registered VEuPathDB login](../decisions/wdk-requires-registered-login.md) |
| An off-topic message gets a two-sentence redirect and no tool | N10 | [An off-topic turn reaches no tool](../decisions/an-off-topic-turn-reaches-no-tool.md) |
| A statement or a question about one gene builds nothing | N12, S15 | [Building is a response to a request](../decisions/building-is-a-response-to-a-request.md) |
| A count question builds the set that answers it | S14 | [A question a search answers is a build](../decisions/a-question-a-search-answers-is-a-build.md) |
| A "no" on an offer card ends the turn with no model reply | N7, V5 | [An offer is a card, not prose](../decisions/an-offer-is-a-card-not-prose.md) |
| The injection screen reads the message text only; an attached image or PDF is not screened. A judgement that cannot be made refuses the message with a 503 | N6 | [One injection judge, and what a failed judgement means](../decisions/one-injection-judge-and-what-a-failed-judgement-means.md) |
| Attachments: 10 MB a file, 20 MB and 6 files a message; images and PDFs only for a model measured to read them | C13 to C16 | [An attachment is a file part the model can read](../decisions/an-attachment-is-a-file-part-the-model-can-read.md) |
| A revert restores the strategy of the target message; the later version stays in the VEuPathDB account | F9 | [A strategy has a revision history](../decisions/a-strategy-has-a-revision-history.md) |
| A strategy from controls is whatever the site's counts support that day; its tree moves with the budget and the candidates that answer | V4 | [A strategy from controls is measured](../decisions/a-strategy-from-controls-is-measured.md) |
| A change to a strategy that exists is an edit, never a rebuild: unchanged steps keep their WDK step ids, and a second "build" on such a conversation is refused in favour of the edit | S9 to S12 | [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md), [an edit is a delta, not a rebuild](../decisions/an-edit-is-a-delta-not-a-rebuild.md) |

## On the backlog

Named as in the [backlog](../backlog/index.md) on 2026-09-24; the list moves as items close, so read it at UAT start.

| Item | What a runner sees | Flow |
|---|---|---|
| The sample of a large transcript step outlasts the read deadline | On a genome-sized result the check says the genes were not sampled (the read is cut at 20 s) | V1 on a large result |
| The seeds of the other sites recover their controls | The toxodb, vectorbase and portal seeds (Settings, `Seeding`) do not recover all their positives from their own trees | A7 |
| A site edit reaches the Lead's briefing | After an edit on the site, the tab is right but the assistant may describe the old analysis | E5 step 4 |
| The Claude models are probed for images and documents | The Anthropic and Google models are not part of UAT; only the OpenAI models are tested | A1, C13 |
| A search report pages transcripts under a gene cap | A variant comparison near 50,000 rows may say it was cut short | V7 |
| The title and the compactor are metered | The quota pill is short by those two calls | A3 |
| A thread on a site the deployment does not serve breaks the list | A deployment that drops a site shows an empty conversation list when a conversation of that site exists | F4 |

## Not in this release

| Absent | Flow |
|---|---|
| A dark-mode switch; the app does not follow the operating system (a host page can set `data-theme="dark"`) | L4 |
| A page that lists gene sets; they live in the thread, `/export` and `/import` | G1 |
| An export of all of a researcher's data; the `Data` tab only deletes | A4 |
| Importing a shared strategy by its public link; `Open a VEuPathDB strategy...` opens the account's own strategies by link or id | S8 |
| A liveness route at `/health/live`; `/health` serves liveness and the version | D2 |
| A per-message model picker in the composer; the model is chosen in Settings and shown on the trace | A1 |

The pre-UAT defects found while writing these flows are not known limits; they are in [findings](findings.md) and must be fixed or moved here in writing.
