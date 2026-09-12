---
type: Backlog
---

# A prior turn's requirements are dropped when the next turn answers a question

**What I did.** On plasmodb, turn 1 asked for "P. vivax genes that are orthologs of Plasmodium gametocyte-expressed proteases with non-synonymous SNPs; combine text and GO evidence for proteases". FRAME hit its ceiling before binding; the Lead asked the user to narrow (which RNA-seq study, what counts as a SNP). Turn 2 answered only those two questions and said "go ahead and build it". On the portal, turn 1 of another thread asked five questions with recommended defaults; turn 2 said "use the recommended defaults".

**What I got.** Turn 1's ledger held the grounded constraint `{kind: combination, "text evidence OR GO evidence", label: "protease evidence combination", user_explicit, hard}` in all 57 ledger updates; turn 2's 57 ledger updates carry no protease constraint at all, and the Lead's FRAME work order read "Operationalize the requested P. falciparum 3D7 gametocyte RNA-seq expression filter and the P. vivax P01 non-synonymous SNP filter". The build returned 1,987 P. vivax genes with no protease criterion and the reply never said the requirement was gone (the gold answer is 257). On the portal, turn 2's FRAME made 22 `search_memory` calls in 22 phrasings looking for what "the recommended defaults" were, bound one criterion and stopped.

**Why that's wrong.** The user's stated question is silently replaced by a narrower one; every count, gene set and export from the thread answers the wrong question, and the reply reads as if the original request were met.

**Why it happens.** The turn's constraints are derived from the current message (`ai/lead/intent.py`), and a turn that ended without a committed spec leaves nothing the next turn merges with; the Lead's own recommendations from the previous turn are not constraints either.

**Fix.** When the previous turn ended unframed (`frame.spec` null, `readyToBuild` false) or with an open question, the new turn's constraints are the previous provisional set merged with the new message's, and a recommendation the Lead offered and the user accepted is grounded as a constraint; only an intent classified as a new goal replaces the set. Red first: two-turn cases for both measured shapes.

**What you'd get.** Turn 2 builds the protease union the user asked for; "use the recommended defaults" binds the five recommended values without a memory search.
