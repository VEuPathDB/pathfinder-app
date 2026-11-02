---
type: Backlog
title: A computed verdict is run live
description: The verifying corpus cases passed on QA; the organism column body read for a root over 2,000 records is still not recorded.
tags: [verification, evals, live]
generated: { by: claude-code/opus-5.5, at: 2026-10-27T00:00:00Z }
status: proposed
---

# A computed verdict is run live

## Where it stands

On 2026-10-31, on QA with Luna, one case at a time, the verifying cases passed with no
failed check: `uat-s2-plasmodb` (116), `uat-s2-fungidb` (64), `uat-s2-toxodb` (78),
`uat-s2-vectorbase` (343), `uat-s2-veupathdb` (116), `uat-n13-plasmodb` (158) and
`orthomcl-singletons-counted-by-organism` (523,795).

A root of at most 2,000 records is counted from its standard report
(`ai/lead/verify_checks.py::_paged_organisms`). A larger root is counted with the byValue
reporter on the `organism` column, and no body of that read is recorded. QA PlasmoDB
answered that reporter with HTTP 500 on 2026-10-28, so the body has to come from a site
that answers it.

## Done when

An organism byValue body for a root over 2,000 records is recorded under
`tests/fixtures/wdk` from a site that answers it, and the check reads it in a unit test.
