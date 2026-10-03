---
type: Backlog
title: A carry to orthologs is one transform
description: A request to carry a result to its orthologs in another organism is built as an orthology round trip that keeps the source organism, so the result is not the target organism's genes; the words "carry to", "map to" and "orthologs in X" name one transform whose result is X's genes.
tags: [frame, orthology, structure]
generated: { by: claude-code/opus-5, at: 2026-10-02T00:00:00Z }
status: proposed
---

# A carry to orthologs is one transform

**What I did.** On the portal, built "Plasmodium falciparum 3D7 genes with a predicted signal peptide and 2 to 99 transmembrane domains" (116 genes), then "Carry these to their syntenic orthologs in Toxoplasma gondii ME49."

**What I got.** The tree became `((SP INTERSECT TM) INTERSECT GenesByOrthologs(GenesByOrthologs(copy of SP INTERSECT TM)))`: a round trip that keeps the P. falciparum genes, with the transform at 0 genes and the facts row "Organism took 0 of the 0 entries that match 'Toxoplasma gondii ME49'".

**Why that's wrong.** The researcher asked for ME49 genes; the strategy returns P. falciparum genes filtered by having a syntenic ortholog, and the organism the transform was told to reach shows as matched by no entry.

**Why it happens.** The orthology rules in `domain/strategy/orthology.py` know two shapes, a transform out and a round trip that keeps the source, and nothing reads the message's words to choose: "carry these to their orthologs in X" is the transform whose result organism is X, while "keep only the genes that have an ortholog in X" is the round trip. The portal's `GenesByOrthologs` organism vocabulary also matched no entry for the ME49 label the message used.

**Fix.** A domain reader beside `named_combine.py` classifies the orthology request from the message (carry / map / translate to X: a transform whose result is X; have an ortholog in X / conserved in X: the round trip); `set_structure` refuses a round trip when the message asks for a carry, and the reverse, naming the shape the words ask for. The organism entry the transform runs on is matched through the same stated-organism rule the binds use, and a label the vocabulary lacks is a refusal that names the nearest entries.

**What you'd get.** `GenesByOrthologs((SP INTERSECT TM))` with the organism ME49 stated, and the result counted in ME49 genes.
