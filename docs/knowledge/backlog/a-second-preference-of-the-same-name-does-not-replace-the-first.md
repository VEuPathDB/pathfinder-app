---
type: Backlog
---

# A second preference of the same name does not replace the first

**What I did.** The dev account holds two `preference` memories, both named "Default organism": one written 2026-08-31 with content `{"organism": "P. falciparum 3D7"}`, one written 2026-09-12 with `{"organism": "Plasmodium berghei ANKA", "scope": "default unless user says otherwise"}`. On plasmodb, in a new thread on the rebuilt stack (the runtime now retrieves every preference at turn entry, whatever the request is about): "Find genes with a predicted signal peptide and at least one transmembrane domain. Give me the count."

**What I got.** The retrieval returns both preferences at the head of the list (measured directly against the store: `preference | Default organism | Plasmodium berghei ANKA`, then `preference | Default organism | P. falciparum 3D7`). The turn built the count for P. falciparum 3D7 (479 INTERSECT 1,628 = 288) and said so without mentioning that a default was applied or that two disagree.

**Why that's wrong.** The researcher stated a default and later changed it. Nothing in the product records that the second statement replaced the first, so the pinned memories carry a contradiction and the turn silently picks one. The older statement is the one that won.

**Why it happens.** `ai/tools/standalone/memory_tools.py::remember` calls `MemoryStore.put` with no key, and `put` mints `uuid4()` when the caller passes none (`assistant-platform: packages/assistant-core/src/assistant_core/memory/store.py`), so every `remember` writes a new row whatever its name and kind. Nothing supersedes, and the retrieval has no rule for two memories of one kind with one name.

**Fix.** A memory of a kind that states a standing fact is keyed by what it states, not by a fresh id: `remember` writes a `preference` under a key derived from its name for that user (a slug of the name), so a second statement of the same preference replaces the first and the store holds one. The kinds that accumulate (`case`, `strategy`, `gene_set_note`, `knowledge`) keep the minted key. The tool's reply says which it did, "Stored" against "Updated". Red first: two `remember` calls with kind `preference` and the same name leave one row carrying the second content, and the same two calls with kind `case` leave two.

**What you'd get.** The turn reads one default, applies P. berghei ANKA, and says which default it used.
