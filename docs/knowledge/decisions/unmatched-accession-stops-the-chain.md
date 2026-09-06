---
type: Decision
title: An unmatched accession stops the chain
description: A named identifier absent from the vocabulary is a contradiction, not an ambiguity, so it must not fall through to semantic matching.
tags: [agents, parameters, wdk-alignment, data-integrity]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/fable-5, at: 2026-08-17T00:00:00Z }
status: stable
---

# The failure

Asked on a real account for "P. falciparum 3D7 genes that are kinases, identified by InterPro domain PF00069", the built step was:

```json
"domain_accession":  "PF00069",
"domain_database":   "INTERPRO",
"domain_typeahead":  ["IPR000023 : Phosphofructokinase_dom"]
```

It searched **phosphofructokinase**. Two genes came back instead of ~81, and verification reported success. A researcher reading "kinases with a signal peptide: 3 genes" had no way to see the wrong domain.

# Why it happened, confirmed against live WDK

`PF00069` is a **Pfam** accession. `domain_typeahead`'s vocabulary is **dependent on `domain_database`**: with `INTERPRO` selected it holds 5,405 `IPR` entries, and `PF00069` is genuinely absent (the InterPro equivalent is `IPR000719`).

So the chain ran:

1. FRAME set `database=INTERPRO` (following the user's word "InterPro") alongside a Pfam accession -- an inconsistent pair.
2. The dependent vocabulary refreshed to IPR-only.
3. `accession_in_text` found no match, and **fell through** to the semantic tier.
4. Embedding similarity matched on the substring "kinase" inside "Phosphofructo**kinase**".

Step 3 is the defect. FRAME's own instruction already says that when a value is not in the vocabulary the search *cannot* realize the criterion -- choose another search or drop it, "never guess a value and never invent one". The resolver did the opposite.

# The rule, as first implemented

`names_absent_accession` returned True when the text named an accession and none of them appeared in the vocabulary. `map_intent_to_value` then returned `None`, opening a Tier-3 slot, instead of consulting the fuzzy tier. Both symbols were deleted on 2026-08-17 and the guarantee moved; see the amendment below.

The distinction that matters: an accession is an **exact** reference. Absent from the vocabulary it is a contradiction to surface, not an ambiguity to resolve by similarity. Text carrying no accession is unaffected and still uses the rule and semantic tiers.

# What it did in practice

Re-running the same request after the fix, the model reconciled its own inconsistency rather than being handed a guess:

| | before | after |
|---|---|---|
| `domain_database` | `INTERPRO` | `PFAM` |
| `domain_typeahead` | `IPR000023 : Phosphofructokinase_dom` | `PF00069 : Pkinase` |
| genes | 2 | 81 |

Blocking the guess did not just avoid a wrong answer; it pushed the model to fix the database to match the accession.

# Amended 2026-08-17

The decision holds; the mechanism that carried it is gone. There is no fuzzy tier
left to fall through to, because there is no tier that reads the text at all
([one proposer, one validator](one-proposer-one-validator.md)). The same
guarantee is now structural and covers every value rather than accessions alone:
a value proposed for a parameter with a vocabulary must match an entry exactly,
by term, by label, or by an accession exactly one entry carries, or the call is
refused with the nearest entries named. A
similar-looking entry can no longer be substituted for the one the request
asked for, because nothing computes similarity on the binding path.

The one case the old rule handled that the new one must state out loud: an
accession that is real but absent from the shortlist the sheet shows. The sheet
states the vocabulary's true size and names
`get_parameter_options(search_name, param, query=)`, so a shortlist miss is a
lookup, not a guess. An accession that is absent from the vocabulary itself
still stops the chain, which is what this file is about.

# Amended again: an accession alone is the entry

WDK writes a typeahead term as `<accession> : <label>`, so `PF00069` and
`PF00069 : Pkinase` name one entry. Exact matching refused the first form, and
the retry beside it listed `PF00569 : ZZ` and `PF00169 : PH` ahead of the entry
the accession identifies, so the model changed the database rather than the
value and bound `IPR000023 : Phosphofructokinase_dom` - the wrong bind this file
opens with, reached from the opposite direction.

Three things changed together, because each one alone leaves the loop open:

- A proposal that is the leading accession of **exactly one** entry names that
  entry. Two entries sharing it is an ambiguity: the refusal names the entries
  that share it and asks for the full value of the one meant. An accession
  holds a digit and is at least four characters, so a leading word such as
  `Plasmodium` is a label and never a match.
- The nearest entries lead with the ones the proposal starts, so `PF0006`
  answers with `PF00069 : Pkinase` rather than with the closest characters.
- The sheet pins an entry whose accession the request writes as a word, not only
  one whose whole term the request writes out.

# Anchor

`ai/tools/standalone/frame_spec.py:_refuse_unmatched_value`, ranking through
`domain/parameters/wdk_vocab.py:nearest_entries`, which is the one ranker every
did-you-mean uses, guarded by
`veupathdb-py/tests/unit/domain/parameters/test_wdk_vocab.py`.
Guarded by `TestAProposedValueMustBeOnTheSheet::test_a_substring_of_an_entry_is_not_a_match`
and `tests/unit/ai/tools/test_frame_proposals.py`.
Matching is `veupathdb/domain/parameters/wdk_vocab.py:match_exact_option` over
`leading_accession_token`, guarded by
`veupathdb-py/tests/unit/domain/parameters/test_wdk_vocab.py`; the pin is
`veupathdb_mcp/catalog/param_sheet.py:_is_named`, guarded in
`veupathdb-mcp/tests/unit/catalog/test_param_sheet.py`.
