---
type: Backlog
title: The corpus scorer reads a combine without operand order
description: The corpus compares an INTERSECT or a UNION with its operands in order, so the same strategy built with its inputs swapped fails its case.
tags: [evals, corpus, scoring]
generated: { by: claude-code/opus-5, at: 2026-10-04T00:00:00Z }
status: proposed
---

# The corpus scorer reads a combine without operand order

**What I did.** Ran the corpus case `uat-dry-b-fungidb` on fungidb.

**What I got.** `structure: expected '(GenesByGoTerm INTERSECT GenesByOrthologPattern)',
got '(GenesByOrthologPattern INTERSECT GenesByGoTerm)'`, a fail.

**Why that's wrong.** Both trees return the same genes, so the case reports a
failure the researcher would never see, and the corpus pass rate understates the
product.

**Why it happens.** The structure the scorer compares is written with each
combine's primary input first, and INTERSECT and UNION are compared as written.

**Fix.** Write the two inputs of an INTERSECT or a UNION in a fixed order before
comparing; MINUS keeps its order.

**What you'd get.** The case passes on either input order and still fails on a
different operator or search.

**Also remaining.** `sameRecordsAs` compares `TurnFacts.record_ids`, the listed
records and then every record a check read. On hostdb, `uat-dry3-d-hostdb` listed
the same five genes in its third and fourth turns (ENSMUSG00000035929,
ENSMUSG00000060550, ENSMUSG00000067212, ENSMUSG00000073409, ENSMUSG00000079507),
and the case failed because the third turn's check had also read three more
records. The comparison reads the listed records of each turn.
