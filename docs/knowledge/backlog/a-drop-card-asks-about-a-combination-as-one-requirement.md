---
type: Backlog
title: A drop card asks about a combination as one requirement
description: A request that joins two properties with "and" can be held as one combination requirement with no requirement for either part, so the drop card offers to drop the part the site can search together with the part it cannot.
tags: [frame, classifier, requirements, consult]
generated: { by: claude-code/opus-5.5, at: 2026-10-13T00:00:00Z }
status: proposed
---

# A drop card asks about a combination as one requirement

## What I did

One turn on the QA PlasmoDB site, new conversation: "Find Plasmodium falciparum
3D7 genes with a predicted GPI anchor and a signal peptide."

## What I got

The classification held two stated requirements:

| kind | requested value |
|---|---|
| organism | Plasmodium falciparum 3D7 |
| combination | predicted GPI anchor AND a signal peptide |

FRAME reported `R2`, `site_has_no_search`. The card asked: "No search on this
site states 'predicted GPI anchor AND a signal peptide'. Drop it from the
request?" with the options "Drop predicted GPI anchor AND a signal peptide" and
"Keep predicted GPI anchor AND a signal peptide". The reply beside the card
said the site can search for signal peptides.

## Why that's wrong

The site has a signal peptide search and no GPI anchor search. The card has no
option that drops the GPI anchor and keeps the signal peptide, which is the
only strategy the site can build. "Drop" removes both properties and "Keep"
builds nothing.

## Why it happens

`numbered_requirements` (`domain/strategy/requirement_reports.py`) numbers every
stated constraint, and the classification stated the combination with no
constraint for either of its parts, so the one number FRAME can report names
both properties.

## Fix

Not chosen. Two candidates: the intent gate refuses a stated combination whose
parts are not stated requirements of their own, or the numbered list leaves a
combination out and numbers its parts. Replay the saved classifier requests
before choosing.

## What you'd get

Three requirements: the organism, "predicted GPI anchor" and "signal peptide".
FRAME reports the GPI anchor alone, and the card asks "No search on this site
states 'predicted GPI anchor'. Drop it from the request?".
