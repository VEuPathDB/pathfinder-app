---
type: Decision
title: An obsolete term is refused only when it counts nothing
description: A vocabulary pick the site labels obsolete binds when the site counts records for it and carries its label; a bind that counts 0 is refused with the ontology's mark and the nearest current entries, and a term the researcher named is replaced only through a card.
tags: [frame, parameters, vocabulary]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: stable
---

# What was decided

A pick whose site label holds the word "obsolete" is read like any other pick:
it binds, it is counted, and its label ("GO:0031225 : obsolete anchored component
of membrane : 0") is recorded, so the facts part and the reply show the mark
beside the count. The bind is refused only when the site counts 0 records for
it at the bound values and the pick was not the site's own default. The refusal
states what the site showed: the ontology marks the term obsolete and the site
counted 0 genes. It names no count it did not read, and it names no
replacement, because the label carries none. When the researcher named the term
(a stated or card value), the refusal asks FRAME to put the choice on a card,
with the current entries nearest the term's words as its options; when FRAME
chose it, FRAME may pass one of those entries itself.

# What was rejected

**Refusing every obsolete pick at the label read.** The first rule refused the
pick before it was counted and said the term "annotates few or no records". On
fungidb GO:0031225 answers 82 genes (organism Candida albicans SC5314, curated
and computed evidence), and the trailing number of its label is 0, so the claim
was false. The refusal listed "extrinsic component of membrane" entries by word
overlap, FRAME bound GO:0019898 (80 genes, a different concept), and the
researcher's count fell from 58 to 5.

**Naming the ontology's replacement.** The label is the only site data the bind
holds, and it names no replacement; a replacement read from outside the site
would be a claim the facts cannot show.

# Anchor

`ObsoletePick.refusal` and `obsolete_picks` in
`services/strategies/obsolete_terms.py`; `record_and_count_criterion` in
`ai/tools/standalone/_frame_count.py`. Guarded by
`tests/unit/ai/tools/test_an_obsolete_term_binds_by_its_count.py` and
`tests/unit/services/strategies/test_an_obsolete_term_is_named_at_bind.py`.
