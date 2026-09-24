---
type: Decision
title: A criterion says why its search was chosen
description: FRAME passes a typed why (basis, term, one line of reason) on the binding call; set_criterion checks it against the catalog read it recorded and writes the searches that read answered beside the bound one, with their similarity and the call id. The record rides StepWords to the canvas, the step editor, the rail, the ledger and addedSearches, and unnamed_search refuses once a reply that names a search without its term beside it. Prompting for verbosity, a free-text rationale with no alternatives, and a reason rendered in the reply only were rejected.
tags: [frame, turn-contract, catalog, strategy-graph, naming]
generated: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
status: stable
---

# What was decided

**The catalog read is recorded whole.** `search_for_searches`, `list_searches`
and `list_transforms` each put a `CatalogRead` on `AgentToolState.catalog_reads`:
the tool call id, the query, the record type and every hit in order, in plain
text, with `semanticSimilarity` for a ranked read. The transform refusal records
the listing it names. The enum guard reads the same store.

**The binding carries a checked reason.** `set_criterion(why=...)` takes a
`SearchChoice`: a basis (`parameter`, `organism`, `record_type`, `only_match`,
`nearest`), the term that decides it, one line of reason holding the term, and
the references a research read of this turn returned that the choice rests on.
The tool writes `Criterion.rationale` (`SearchRationale`,
`domain/strategy/step_rationale.py`) from the newest read of the pass that
answered the bound search: its score, the first three other hits of a ranked
read with theirs, how many searches the read answered, the query and the call
id. It refuses, and records nothing, when no read of the pass answered the
search, when a new binding carries no `why`, when the reason names a site search
the read did not answer (a search name, or a display name of two or more words),
when the data the call holds does not back the basis, when the reason does not
hold the term, and when a cited reference is not one this turn retrieved. A
value edit on the search the criterion already runs keeps its reason; a
re-binding replaces it.

**No check reads a threshold.** `nearest` compares the bound hit with the other
hits of the same read: an order, not a cut. It refuses a claim, never a binding,
so [a step says what runs](a-step-says-what-runs.md) stands.

**An analysis step's reason is derived.** `AnalysisRationale.of(binding)` states
the compute the exported document holds (the method, else the first subset
filter, and the binding's words). It is never stored, so it reads the same
wherever the document is read, a re-import included.

**One record, many readers.** `StepWords` carries `rationales` beside the
criterion texts and the analysis kinds, and is the one value the commit, the
build and the export pass to the graph. `StepResponse.rationale` serves it, the
canvas node draws `why: <short>` under the subtitle with the reason and the
compared searches on hover, the step editor's results section opens with it, the
rail's criterion card shows it before anything is built, the Lead's ledger
prints a `WHY` line, and `addedSearches` and the out-of-budget reply carry it.
The case memory records the basis and the searches it was chosen over, never the
free-text reason. The eval extract carries the reasons and redacts them with the
researcher's stored words.

**The reply gives the reason beside the name.** `unnamed_search`
(`ai/lead/search_reasons.py`) refuses, once, a reply that names an added search
with a recorded reason and does not hold the reason's term in the same paragraph
or list item. The correction hands over the recorded line, so the retry quotes
the grounded record.

# What was rejected

**Prompting for verbosity.** The reply is written from the ledger and
`addedSearches`; a prompted reason is composed from nothing the turn recorded,
fluent and unverifiable.

**A free-text rationale with no alternatives.** FRAME could write "chosen over
X" about a search it never saw. Only the tool holds the read, so only the tool
writes the alternatives, and a list the model types would need the same check.

**Rendering in the reply only.** The reason would be gone on the canvas, on
reload and on the next turn, and the contract would have no record to hold the
prose to.

**A parallel `rationales` dict threaded beside the criterion texts.** Two
mappings through every write site drift; one `StepWords` value carries both.

**Persisting catalog reads across turns.** More state for a path the FRAME
procedure already rules out; the refusal names the one call that fixes it.
