---
type: Backlog
title: An upper bound alone keeps no default lower bound
description: Asked for proteins under 30 kDa, the Molecular Weight search kept the site's default minimum of 10,000 Da, so proteins under 10 kDa were left out while the reply called the result the requested range.
tags: [parameters, ranges, reading]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: proposed
---

# An upper bound alone keeps no default lower bound

## What I did

Asked on QA MicrosporidiaDB, on Luna: "Encephalitozoon cuniculi GB-M1 genes with a
predicted signal peptide and a molecular weight under 30 kDa."

## What I got

Strategy 214650970: Predicted Signal Peptide (93) INTERSECT Molecular Weight (926)
= 31 genes. The Molecular Weight step bound `min_molecular_weight = 10000`,
`max_molecular_weight = 30000`. VERIFY passed. The reply named the 10 kDa floor as
a caveat.

## Why that's wrong

"Under 30 kDa" has no lower bound. Signal-peptide proteins under 10 kDa are left
out of the 31 genes, so the count answers 10 to 30 kDa, not the question.

## Why it happens

FRAME binds the stated upper bound and leaves the other end of the range at the
site's published default, which is 10,000 on this search.

## Fix

Not decided. A range the user bounds on one side binds the other side at the
parameter's published minimum or maximum, not its default; measure the count with
`min_molecular_weight` at the published minimum.

## What you'd get

The count of signal-peptide genes from 0 to 30 kDa in E. cuniculi GB-M1, 31 or
more. The suggested question now states both bounds.
