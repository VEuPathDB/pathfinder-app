---
type: Decision
title: One proposer, one validator
description: The model reads the whole parameter sheet and proposes a value or a null for every visible parameter; the DAG walk validates and binds. The English-reading rules and the injected per-parameter resolvers are deleted, and the sheet shortlists by word overlap rather than by embedding.
tags: [agents, parameters, architecture, measurement]
generated: { by: claude-code/fable-5, at: 2026-08-17T00:00:00Z }
verified: { by: claude-code/fable-5, at: 2026-08-17T00:00:00Z }
status: stable
---

# What was decided

Parameter values have exactly one author and exactly one judge.

**The proposer is FRAME.** `set_criterion` called with no `params` returns the
parameter sheet: every visible parameter with its name, display name, type,
help, default, bounds, dependency and vocabulary. It records nothing, and it
registers the search in the discovery gate. The same tool called again with
`params` takes one entry per visible parameter, and the model writes a value or
a `null` for each of them in a single call.

The sheet is returned by the binding tool rather than by `get_search_overview`
because it has to be the tool result immediately before the proposal. A sheet
read many calls earlier is out of the model's working set by the time it
proposes, which is what let invented parameter names through.

The sheet call also returns `params_template`, every visible parameter name in
sheet order mapped to `null`, serialized before the sheet itself. It is the exact
`params` object to send back. Three live runs invented the same seven parameter
names in the first proposal after reading the sheet, so the contract stopped
asking the model to compose the object and hands it one to copy.

One WDK read serves both the sheet and the registry entry, so the two can never
name different parameters. A **second** sheet for the same criterion and search
comes back with every parameter but no vocabulary, and a note pointing at
`get_parameter_options`: the model already holds the values, and re-sending nine
vocabularies twice cost 838K tokens in one turn. Every refusal now says the valid
names are listed above and not to request the sheet again, for the same reason.

**The judge is the DAG walk.** It owns names, types, vocabulary membership,
dependency order, contrast structure, degenerate pairs, hidden parameters and
the wire form. Nothing else reads the request.

The clauses are in `set_criterion`'s docstring and in the four test classes
named under Anchor. What those do not say is why the contract has this shape,
and there are three invariants behind it:

- **Silence is not an answer.** Every visible required parameter must be decided,
  and `null` is a decision - it means "the request does not determine this", and
  it binds the disclosed default or opens a slot. A parameter simply left out is
  a retry. The failure this replaces is a default that answered a question
  nobody knew had been asked, which is also why a stated quantity left `null`
  comes back `unread` rather than defaulting.
- **A refusal must be recoverable in the same turn.** Every rejection names what
  was wrong and what to write instead: the real parameter names, the nearest
  vocabulary entries, the fresh vocabulary a dependent's parents produced
  (`redecide`). A
  retry the model cannot act on ends the turn, so nothing here refuses without
  a candidate.
- **The tool surface may not be a second source of error.** Numbers and
  JSON-encoded lists are coerced rather than refused, because a rejection the
  model reads as a WDK verdict makes it report a failure that never happened.
  What is *not* coerced is meaning: a vocabulary value must match an entry
  exactly - by term, by label, or by an accession exactly one entry carries -
  and a near miss is a question rather than a substitution.

# The three things that were rejected, and what each one measured

The corpus is the 20 gold strategies: 70 steps, 332 scored parameters, one
unreachable step recorded and skipped. `exact` is split by where the value came
from, because that split is the whole argument.

| arm | exact | wrong | asked | unset |
|---|---|---|---|---|
| the sheet, one call per criterion (production) | **285** (stated 222, defaulted 63) | 18 | 20 | 9 |
| no proposer at all, the walk alone (the floor) | 154 (defaulted 154) | 48 | 115 | 15 |

**Rejected: language rules in Python.** The rules read the criterion text for an
organism, a direction, a polarity, a comparator, a quoted term, an identifier.
On the recorded baseline they bound **13** of 332 parameters. The other 155 of
that arm's 168 exact values were WDK defaults that happened to equal the gold
value, which is why the arrangement scored 50.6 percent and why every live run
found rule N+1: the rules were never carrying the corpus, the defaults were.
Each new rule also had to be argued against the others, since a number in the
text belongs to one of five numeric bounds and no rule available to our code
says which.

**Rejected: an injected LLM resolver per parameter.** Two agents, one for
vocabularies and one for free values, called per unresolved parameter. Three
findings killed it. It was **discarded in production**: `set_criterion` called
the walk without `bind_inferred`, which defaults to false, so every inferred
match was dropped and the WDK default bound instead, at two model calls per
parameter for no effect. It **never saw the vocabulary it was designed for**:
`allowed_values` was capped at 50 entries, so a 5,461-entry vocabulary was
presented to it as its first 50. And when it was allowed to bind, it scored
**205** against its own floor of 184: twenty-one parameters, bought at two model
calls for every unresolved parameter. The sheet scores 285 against a floor of
154, at one call per criterion. (The two floors differ because the
scorer became kind-aware and because a held-back numeric default now counts as a
question rather than as a silent bind. Compare each arm with the floor measured
beside it, never across the two columns.)

**Rejected: embedding the vocabulary to shortlist inside the sheet.** The design
called for the 200 nearest entries by cosine. Measured in the api container,
embedding 5,461 texts takes **238 seconds** and 500 texts takes 21, so a
synchronous embed inside a tool call costs the user four minutes on one
parameter. The sheet shortlists **lexically** instead: entries whose label
shares words with the goal, with any entry the request names - in full, or by
the accession it starts with - pinned to the front, capped at 200, and a note that states the true total and points at
`get_parameter_options(query=)`. A vocabulary of 200 or fewer is sent whole, so
ranking cannot lose anything the model could have used.

# What stays, and why it is not the same kind of rule

The walk keeps every rule that encodes WDK's structure rather than English: the
topological order with a re-fetch under bound parents, curated multi-pick
defaults, hidden-parameter defaults, the refusal to inherit a free-text query's
default, the vocabulary ledger and its degenerate-pair rule, the contrast roles,
filter parsing, phyletic handling and the wire encoding. Those are falsifiable
against WDK and are tested against it. A rule that reads a sentence is
falsifiable only against a corpus of sentences, which is the model's job.

# The risks the measurement surfaced, and where each is caught

Eighteen wrong values, every one inspected.

| risk | what it looked like | where it is caught |
|---|---|---|
| a transform's target organism swapped with the seed's source | an ortholog transform over-selected its target | the criterion role is on the sheet and in `set_structure`; the bound value is disclosed in `resolved_params` |
| multi-pick under-selection | one of two trophozoite assays; a subset of `text_fields` | sheet wording, and the bound list is disclosed rather than summarized |
| genus against strain | `Plasmodium` against `Plasmodium falciparum 3D7` | the criterion text carries it, the value binds as stated and is visible; an ambiguity is a question, not a rule |
| either/or parameter pairs | a free-text half filled beside a typeahead pick | WDK-SITE-007 (`veupathdb-py: docs/knowledge/wdk/rules/site-model-params.md`), which names the authoritative half and measures what filling both costs |
| `GenesByOrthologPattern` | 7 of the 18, six of them structural | caught by a contract of its own, taken after this measurement: the model proposes the two species lists against the clade tree and `profile_pattern` is derived from them, which moved the same arm to 288 exact and 15 wrong ([the two lists are the proposal](phyletic-lists-are-the-proposal.md)) |

The two that are not on this list and were expected to be: no proposal named a
parameter the search does not have, and no proposal was refused by a vocabulary,
in the whole 70-step run.

# Anchor

`veupathdb_mcp/catalog/param_sheet.py:build_sheet` for the sheet;
`ai/tools/standalone/frame_spec.py:set_criterion` for the contract, guarded by
`TestAProposedValueMustBeOnTheSheet`, `TestEveryVisibleRequiredParamIsDecided`,
`TestADependentVocabularyIsRedecided`, `TestAStatedQuantityLeftNullIsARetry`,
`TestTheSheetComesBackFromSetCriterion` and
`TestASecondSheetDropsTheVocabularies`
in `tests/unit/ai/tools/test_frame_spec.py`;
`ai/tools/standalone/_catalog_models.py:register_search` is the only write to the
discovery gate from a WDK search definition;
`veupathdb_mcp/catalog/param_dag.py` for the walk. The figures above were measured
by hand against `thesis/eval/gold_strategies`, at one to two model calls per
step; no gate re-runs them. This decision is wrong the day the tests named above
stop holding, or the day a fresh scored run over that corpus stops beating the
floor by a wide margin.
