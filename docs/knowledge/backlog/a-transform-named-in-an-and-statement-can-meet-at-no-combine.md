---
type: Backlog
---

# A transform named in an AND statement can meet at no combine

**What I did.** On the portal (veupathdb) in the web app, a new conversation: "Start from Toxoplasma gondii ME49 genes with a predicted signal peptide, transform them to their Plasmodium falciparum 3D7 orthologs, then keep only those orthologs that are expressed in the top 20% during gametocyte stages, and finally remove any that also have an ortholog in Cryptosporidium parvum Iowa II. How many genes remain?" Thread `6acbbb4f-bf98-4389-9b4d-0d9e2e4e5f09`.

**What I got.** FRAME bound four criteria (`signal`, `ortholog_map` with role transform, `gametocyte_expression`, `exclude_crypto`) and called `set_structure` with `((transform(signal) INTERSECT gametocyte_expression) INTERSECT exclude_crypto)`. The call was refused three times with the same text: "The structure is refused: the user requires 'predicted signal peptide AND transform to Plasmodium falciparum 3D7 orthologs AND top 20% expressed during gametocyte stages AND remove any with a Cryptosporidium parvum Iowa II ortholog': those criteria must meet at INTERSECT, but the tree joins them at no combine node. Restate the tree so those criteria sit under one INTERSECT branch, and combine that branch with the rest." The turn then ended with the error chunk "Tool 'set_structure' exceeded max retries count of 3" and the reply "I couldn't produce a response for this turn. Please rephrase or provide more context and I'll try again." 196 s, $0.08, no strategy.

**Why that's wrong.** The tree FRAME sent is the one the request describes; no tree can satisfy the refusal, because a transform is a node on the path and not a member of a combine. A well-formed four-step request on the portal ends with nothing and a message that blames the researcher's wording.

**Why it happens.** `domain/strategy/combination_check.py::match_terms` matches the statement's terms to any criterion, the transform criterion included, and `_meeting_combine` then looks for a combine that brings the transform as a member, which no structure has; `meeting_operator`'s own rule ("a transform the statement does not name is transparent") stops applying the moment the intent classifier's `combination` constraint names the transform, as it does for any request that says "transform ... then ...".

**Fix.** Terms match `filter` and `seed` criteria only; a transform is transparent whether the statement names it or not, and `constraint_grounding._ground_combination` records a term that matched a transform as satisfied by the transform's presence on the path from the named criteria to the root (or abstains when it is not on that path). Red first: the measured statement and structure pass `combination_violation`; the same statement over a tree that joins the two filters at UNION is still refused.

**What you'd get.** `set_structure` accepted on the first call, the strategy built, and a count.
