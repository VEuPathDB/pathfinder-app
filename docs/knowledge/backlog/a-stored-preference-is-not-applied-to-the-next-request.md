---
type: Backlog
---

# A stored preference is not applied to the next request

**What I did.** On plasmodb in the web app: thread 1, "Remember that I work on Plasmodium berghei ANKA, not P. falciparum, unless I say otherwise." Thread 2, a new conversation: "Find genes with a predicted signal peptide and at least one transmembrane domain. Give me the count."

**What I got.** Thread 1: intent `memory_request`, `remember(kind="preference", name="Default organism", content={"organism": "Plasmodium berghei ANKA", "scope": "default unless user says otherwise"})`, reply "Stored. I'll use Plasmodium berghei ANKA as your default organism in future work". Thread 2: the turn's event log holds no `data-memory-retrieved` chunk (nothing was retrieved at turn entry); the Lead's own `search_memory` found "5 memories for genes with predicted signal peptide and at least one transmembrane domain count" (case notes); FRAME bound both searches and the reply asked "I need the organism because the count depends on it. Which should I use? Plasmodium; Plasmodium falciparum 3D7 (recommended if you mean the strain from your earlier work); another".

**Why that's wrong.** The researcher stated a standing default one message earlier and was told it would be used; the very next request asks the question the default answers, and the recommended value is the organism they said they do not work on.

**Why it happens.** `ai/graph/_lead_turn.py::retrieve_memories` reads the top 8 memories across every kind by similarity to the request text (`query=state.user_prompt, kinds=MEMORY_KINDS, top_k=8`); a preference about a default organism is not similar to "signal peptide and transmembrane domain", so it never enters the pinned memories, and nothing else reads preferences.

**Fix.** Preferences are retrieved by kind, not by similarity: every `preference` memory of the user is pinned at turn entry (they are few and short), and the top-k by similarity fills the rest from the other kinds. FRAME's organism resolution reads the pinned preference before it asks. Red first: a domain state with one stored preference and a request naming no organism has the preference in the retrieved set and `organism_hints` carries it.

**What you'd get.** Thread 2 builds the P. berghei ANKA count without a question, and says which default it applied.
