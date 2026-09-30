---
type: Backlog
title: The vocabulary caps live beside the rule that reads them
description: veupathdb-mcp's param_formatting decides how many vocabulary entries a parameter read shows, but imports the two caps as private names from vocab_rendering; one module owns both the caps and the decision in the next tag.
tags: [veupathdb-mcp, catalog, library]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# The vocabulary caps live beside the rule that reads them

**What I did.** Read `src/veupathdb_mcp/catalog/param_formatting.py` in the
`VEuPathDB/ai-wdk-mcp` clone at `v0.2.0a35`.

**What I got.** `param_formatting.py:27-28` imports `_MAX_NARROWED_ENTRIES` and
`_MAX_VOCAB_ENTRIES` from `vocab_rendering.py:19,21`, and `param_formatting.py:293`
chooses between them (`_MAX_VOCAB_ENTRIES if lookup is None else
_MAX_NARROWED_ENTRIES`) before `_capped_vocab_fields` cuts the list.

**Why that's wrong.** A private name crosses a module boundary: a change to either
cap in `vocab_rendering` changes what `param_formatting` shows, and nothing in
`vocab_rendering` reads them. The number of entries a researcher's read shows
(50 whole, 300 narrowed) has two owners.

**Why it happens.** The caps stayed in `vocab_rendering` when a34 moved the cut
from `vocab_rendering.allowed_values` into `param_formatting._capped_vocab_fields`.

**Fix.** Move both caps into `param_formatting.py` beside `_capped_vocab_fields`
(or give `vocab_rendering` a public function that returns the cap for a read), in
the library's own repository, and tag a new release; then move the pin here.

**What you'd get.** No private import in `param_formatting.py`; the unit tests in
`tests/unit/catalog/test_a_narrowed_vocabulary_travels_whole.py` unchanged
(66 of 66 narrowed, 50 of 3745 whole).
