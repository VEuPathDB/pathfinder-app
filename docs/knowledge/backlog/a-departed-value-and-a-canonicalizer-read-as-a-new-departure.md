---
type: Backlog
---

# A departed value plus a canonicalizer reads as a new departure

**What I did.** With the five-criterion toxodb spec loaded (criterion `step_780fd940`,
"Cell-cycle expression profile similar to MIC2 (TGME49_201780)"), I put the graph in the
state a write that already departed leaves behind: `step_780fd940` holding
`ProfileGeneId = 'TGME49_300100'`. The catalog for this search answers a case-folded
gene id, so validating `TGME49_300100` returns `tgme49_300100`, the way a vocabulary
match rewrites a value. Then I sent `update_leaf_params(step_780fd940,
{"ProfileNumToReturn": "100"})`, which names no value the criterion states.

**What I got.** The patch is refused: "REJECTED: the criterion 'Cell-cycle expression
profile similar to MIC2 (TGME49_201780)' states ProfileGeneId = 'tgme49_201780', and
this write sends 'tgme49_300100', so the strategy would answer a different question. A
value the spec states changes in the spec first (set_criterion, in the framing pass)."
Nothing reached VEuPathDB. With the same catalog and the same graph, the same patch on a
step no criterion states is applied and pushes one `update_step_search_config`, leaving
`{'ProfileGeneId': 'tgme49_300100', 'ProfileNumToReturn': '100'}`.

**Why that's wrong.** The write sent `ProfileNumToReturn` and nothing else. The refusal
names `ProfileGeneId`, which the write never touched and which had already departed from
the spec before the turn began. The stated rule is that a value that already departed
keeps its answer until something restates the criterion, so this refuses an edit the
rule allows, and it names a parameter the caller cannot act on. The researcher's own
change to the result size does not land.

**Why it happens.** `spec_edit_guard.new_value_contradiction` excuses a pair that the
entry graph already held, but the entry pair is measured on the un-canonicalized graph
(`('tgme49_201780', 'TGME49_300100')`) while the pair after the batch is measured on the
canonicalized one (`('tgme49_201780', 'tgme49_300100')`). The two differ only in the
canonicalization, so the batch looks like it introduced the departure.

**Fix.** Canonicalize the entry side the same way the stated side already is:
`update_leaf_params` holds the write's canonical map, so it can pass an entry override to
the commit beside `stated_values`, and `commit._entry_state` reads that instead of the
raw graph for the step the patch names.

**What you'd get.** The patch is applied and pushes one `update_step_search_config`,
leaving `step_780fd940` at `{'ProfileGeneId': 'tgme49_300100', 'ProfileNumToReturn':
'100'}`. A write that does send a stated value is still refused, and a graph that agrees
with the spec is unaffected either way.

Needs a stated value the catalog rewrites (a vocabulary match, a tree-branch expansion or
a closed range) and a departure that predates the write; the wire form is stable for a
plain string and a plain number, so the measured criteria of the spec above do not reach
it on their own.
