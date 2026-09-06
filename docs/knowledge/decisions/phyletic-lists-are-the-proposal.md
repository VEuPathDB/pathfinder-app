---
type: Decision
title: The two species lists are the proposal; the profile pattern is derived
description: On GenesByOrthologPattern the model proposes included_species and excluded_species against the clade tree, and profile_pattern is computed from them and written with them. Exposing the hidden LIKE pattern to the model was rejected because that grammar fails silently and the reference client never lets anyone write it either.
tags: [agents, parameters, site-model, phyletic-profile, wdk-alignment, measurement]
generated: { by: claude-code/fable-5, at: 2026-08-17T00:00:00Z }
verified: { by: claude-code/fable-5, at: 2026-08-17T00:00:00Z }
status: stable
---

# What was decided

`GenesByOrthologPattern` states one criterion - which species must have an
ortholog and which must not - through three parameters. Two of them are visible
free text whose help says "for documentation only", and the third is hidden,
required, and the only one the query reads
(WDK-SITE-006, `veupathdb-py: docs/knowledge/wdk/rules/site-model-params.md`).

**The two visible lists are what the model proposes. The pattern is derived from
them. All three are written together.** No new tool and no new visible
parameter.

The parameter sheet gives `included_species` and `excluded_species` the clade
tree as their vocabulary, built from `phyletic_term_map` and
`phyletic_indent_map`, so a proposal is a code (`pfal`) or a label (`Plasmodium
falciparum 3D7`, case-insensitive) and the sheet shortlists it like any other
large vocabulary. `derive_phyletic_overrides` then resolves both proposals
against that tree and returns three values: the two lists canonicalized to
comma-joined codes, and `profile_pattern` as the census the selection means -
each clade pushed down to the species the census holds, an explicit species
overriding the clade above it, tokens sorted into ascending code order
(WDK-SITE-004 and WDK-SITE-005,
`veupathdb-py: docs/knowledge/wdk/rules/site-model-params.md`). `set_criterion` binds all
three as stated values, so `resolved_params` shows the pattern the search will
actually run.

Three refusals fall out of the same function, and each is recoverable in the
same turn. A term the tree does not carry is a retry naming the nearest codes and
labels. A code in both lists is a conflict, because the census gives one species
one state. An empty selection is a retry rather than a binding: the bare `%` is a
legal pattern that matches every census, so it reads as a phyletic answer and is
not one. **Naming neither list is an empty selection too.** Both lists allow
empty, so silence would otherwise leave the hidden pattern at its published
default and bind by omission the one value this decision exists to derive.

The wire guard stays as the last line rather than being replaced by this. A
pattern that is not a census, or that names a code the tree does not carry, is
still a 422 at build time (WDK-SITE-002, `veupathdb-py: docs/knowledge/wdk/rules/site-model-params.md`),
which is what protects a pattern that did not come from this path.

# What was rejected: make the pattern visible and let the model write it

The alternative is one line of code - drop `profile_pattern` from the hidden set
so the sheet offers it - and it was rejected on four grounds, in the order they
bite.

**The grammar fails silently.** `profile_pattern` is a `string` with no regex and
a 4000-character cap, handed to SQL `LIKE`. Every wrong value is a 200 with a
count, and a value with no `:Y` in it runs a different branch of the query
entirely and returns the ortholog-less genes of the chosen organism under a name
that claims to be a phyletic result
(WDK-SITE-002, `veupathdb-py: docs/knowledge/wdk/rules/site-model-params.md`). A proposer cannot be
corrected by a grammar that never objects.

**One free-text string carries four rules at once.** The codes come from an
865-entry vocabulary that no sheet field advertises; the tokens must be
`code:Y` / `code:N`; they must be in ascending code order or the pattern
describes a census that cannot exist; and only lowercase leaf codes appear in the
census, so a clade code has to be expanded first. Every one of those is `SILENT`
in the rule bundle. Deriving the string obeys all four by construction.

**The reference client never lets a user write it either.** The genomics-site
question form replaces the whole search form, seeds its state from the two lists,
and regenerates the pattern on every change; `PROFILE_PATTERN_PARAM_NAME` appears
twice in that file, at its declaration and inside the write, and there is no
parser (WDK-SITE-006, `veupathdb-py: docs/knowledge/wdk/rules/site-model-params.md`). Writing the pattern
without the lists produces a step that runs correctly and reopens empty.

**It was measured before it was argued.** With the pattern hidden and filled from
`initialDisplayValue`, `GenesByOrthologPattern` was 7 of the 18 wrong parameter
values on the gold corpus: 2 were the pattern at the published default, and 4
were the two lists holding species names where the gold holds codes. The model
was already the weaker author of this value on the runs where it repaired the
pattern by hand at execution time; what it produced was a pattern of its own
devising rather than the criterion it had been given.

# Evidence

Live on plasmodb.org, `organism` at *P. falciparum* 3D7, 2026-08-17:

| `profile_pattern` | totalCount |
|---|---|
| `%hsap:N%pfal:Y%` - present in *P. falciparum*, absent in human | **3,347** |
| `%pfal:Y%` | 5,389 |
| `hsap=1T` - the published default | **0** |

Scored by hand over 20 gold strategies, 70 steps and 332 parameters, proposing
each value:

| arm | exact | wrong | asked | unset |
|---|---|---|---|---|
| before this contract | 285 (stated 222, defaulted 63) | 18 | 20 | 9 |
| after | **288** (stated 226, defaulted 62) | **15** | 20 | 9 |

On both gold `GenesByOrthologPattern` steps the pattern and both lists now score
exact. The one wrong value left on that search is the organism strain, which is a
model choice and not a structural gap.

Live, one turn on plasmodb.org (`.pf-runs/phyletic/turn1`): the phyletic step
bound `%hsap:N%pfal:Y%` with `included_species: pfal` and `excluded_species:
hsap`, after one retry that named the nearest labels for a term the tree did not
carry. The retry is the loop this design depends on, so it is worth stating that
it fired and was answered rather than only that the run ended well.

Re-run on the final image (`.pf-runs/phyletic/turn2`): the model proposed a genus
three times before it proposed a node, each time answered by a retry naming the
nearest codes and labels, and the step then bound the same `%hsap:N%pfal:Y%` with
`defaulted_params: []` - nothing on that step was WDK's choice or PathFinder's.
Three retries on one criterion is the cost this design pays, and it is why the
retry text now says a genus or common name is not a node and points at
`lookup_phyletic_codes`.

# Two findings the work produced on the way, both kept

**A metadata read of this search 500s without the two structural maps.** The
contextual `POST /record-types/transcript/searches/GenesByOrthologPattern`
answers `500 Internal Error` when the context carries `organism` together with
`profile_pattern` and omits `phyletic_indent_map` and `phyletic_term_map`;
either map alone is still a 500, both together are a 200 with
`validation: {level: SEMANTIC, isValid: true}`. "Display purposes only" is a
statement about the query, not about the read. PathFinder now adds the published
default of **every** hidden parameter that allows empty to a metadata read's
context, by shape rather than by name, at all three read sites
(`veupathdb_mcp/catalog/search_context.py:context_for_metadata_read`). The table is in
site-model parameters (`veupathdb-py: docs/knowledge/wdk/model/site-model-parameters.md`).

**Substitution detection had to be corrected in the same work.** When the
contextual read fails, the client falls back to the static `GET`, whose echoed
values are the published defaults - so every value the caller set differs from
the echo, and none of those differences is WDK substituting anything
(WDK-PARAM-008, `veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`). The comparison is
now against the canonical values actually sent, a vocabulary echo is compared as
a set of values, a hidden allow-empty parameter this read supplies is never
reported, and `ResolvedSearch.values_were_read` gates both the comparison and the
validation verdict when the read fell back. Without that, sending the two maps to
fix the 500 would have made them look like values WDK chose.

# Anchor

`domain/parameters/phyletic.py` owns the tree, the resolution, the leaf states,
the pattern and the two lists, tested in
`veupathdb-py/tests/unit/domain/parameters/test_phyletic.py`;
`veupathdb/wdk/phyletic_tree.py:phyletic_tree_of` is the only place that
decides a search is phyletic and builds its tree, so the sheet, the binding and
the wire guard cannot disagree about it;
`veupathdb_mcp/catalog/param_phyletic.py:derive_phyletic_overrides` is the binding,
applied in `ai/tools/standalone/frame_spec.py:set_criterion` and by the bench.
Conformance: `packages/spec/phyletic_conformance.json` is one clade tree and one
expected binding per selection, read by
`apps/api/src/pathfinder/tests/unit/test_phyletic_conformance.py`
and `apps/web/src/features/strategy/editor/widgets/phyleticConformance.test.ts`,
so the two encoders cannot drift apart without a red test on both sides.

`veupathdb-mcp/tests/unit/catalog/test_param_phyletic.py` pins the other half of this
decision - every phyletic string the model reads says the pattern is derived and
must not be written - because a help text that teaches the grammar re-opens the
rejected alternative one prompt at a time.

This decision is wrong the day a criterion needs a pattern the two lists cannot
express. The lists carry three states per species; a count-bearing question such
as "present in at least one mammal" is OrthoMCL's grammar on another site and is
not expressible here at all, by either route.
