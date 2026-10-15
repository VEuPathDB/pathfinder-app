---
type: Backlog
title: A search the site failed to run is reported as missing
description: When the site answers 500 to the search a requirement names, the drop card says no search on the site states it, although the catalog lists that search.
tags: [frame, consult, grounding, orthomcl]
generated: { by: claude-code/opus-5.5, at: 2026-10-15T00:00:00Z }
status: proposed
---

# A search the site failed to run is reported as missing

## What I did

On the QA OrthoMCL site, after three pasted proteins: "OrthoMCL has a 'map proteins
to groups' search that runs Diamond on pasted sequences. Please run it on the three
proteins in my last message."

## What I got

FRAME found `MapProteinsByDiamond` and bound its parameters, and the site answered
`HTTP 500: Internal Error` to each count, also at the site's own defaults with no
value from PathFinder. The card then asked:

> No search on this site states 'OrthoMCL "map proteins to groups" search'. Drop it from the request?

## Why that's wrong

The catalog lists that search and FRAME named it. The researcher is told the site
has no such search and is offered to drop the one thing they asked for, when the
truth is that the site failed to run it.

## Why it happens

Not traced. The requirement is a stated constraint of kind `other`, and the drop card
asks about every requirement the ledger holds as ungrounded, the same path as
[a drop card asks about a requirement the plan answers](a-drop-card-asks-about-a-requirement-the-plan-answers.md).

## Fix

A requirement whose search the site refused is reported as refused, with the site's
answer, not as missing.

## What you'd get

"The site failed to run Map Proteins by Diamond (HTTP 500)", and no offer to drop it.
