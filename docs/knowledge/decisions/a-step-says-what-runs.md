---
type: Decision
title: A step says what runs
description: A search or transform step is titled by the search it runs, with the researcher's words beneath it; set_criterion and the pinned sheet show the bound search's name and summary; the catalog says when no search states the query closely; the Lead's reply names every search the turn added. A similarity threshold that refuses a binding in set_criterion was rejected because the number cannot tell a near miss from a close synonym.
tags: [strategy-graph, naming, frame, turn-contract, catalog]
generated: { by: claude-code/opus-5, at: 2026-09-23T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-23T00:00:00Z }
status: stable
---

# What was decided

**The model and the researcher see what runs, at every place a search is chosen
or reported.** A request can name a property no site search states. FRAME then
bound the nearest search by its search name alone, the canvas titled the step
with the request's words, and the reply called the step by those words, so no
surface said which search ran.

**The binding shows the search.** `set_criterion` returns `whatRuns`: the
search's display name on the sheet-opening call, and the name with the site's
one-line summary once bound. The pinned sheet heading carries the name and the
summary. FRAME binds a search only if its summary states what the criterion asks,
and asks the researcher (`needs_user`, dimension `data_type`, the nearest search
as the recommended value) when no search does.

**The catalog says when nothing is close.** `search_for_searches` puts one
sentence before the ranked list when at least one hit was scored and no scored
hit's absolute cosine (`semanticSimilarity`, from `veupathdb-mcp` v0.2.0a23)
reaches `_FAINT_MATCH`, the tool server's own floor. A hit the index did not
score says nothing about closeness: when no hit was scored, as when the index
does not answer, the sentence says the ranking is by keyword only, and when
nothing matched it says so. The number changes that sentence and nothing else.
`relevance` is relative to the best hit and is documented so.

**A step is titled by its search.** `Criterion.search_display_name` is set by
`set_criterion`, and a leaf or transform built from a criterion carries it as
`display_name`, which the push sends as WDK's `customName`. The researcher's
words ride beside the tree: `StrategyGraph.criterion_texts`, stored in the AST's
`metadata` as `StepWords`, served as `StepResponse.criterionText`, drawn as the
node subtitle and in the step editor header. A restated step keeps its name
unless its search changed, so a researcher's rename survives a value edit.

**A re-import from WDK loses the words.** WDK stores no criterion text.
`services/strategies/wdk_sync.py::upsert_chat` replaces the stored AST with the
one `build_snapshot_from_wdk` reads from the site, which carries no `metadata`,
so a strategy re-imported from WDK holds no `StepWords`: its steps show no
subtitle, and a step it holds is not one the reply rule asks the reply to name.

**The reply names what the turn added.** A build and an edit record the searches
of the steps they added on `TurnMarkers.added_searches` and return them as
`addedSearches`. The turn contract refuses, once, a reply that does not name
each by its display name, and lists them as "<name> (for: <words>)".

# What was rejected

**A similarity refusal in `set_criterion`.** Refusing a binding whose
query-to-search cosine falls under a threshold looks like the direct fix, but
the cosine of a criterion's words against a search's indexed text does not tell
a wrong search from a right one written in other words: a synonym scores low
and a shared vocabulary scores high. A threshold would refuse correct bindings
and pass wrong ones, and the model would learn to reword the criterion until it
passed. The information fix leaves the judgment where it belongs and makes every
surface state the search that runs.

**A substitution note or a forced `needs_user`.** Both need the same threshold
to decide when to fire, with the same failure.

**Titling a step with the request's words.** That title is the cause: the canvas
and WDK both named a search that was not running.
