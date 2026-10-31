---
type: Backlog
title: An audit finding is shown with its evidence
description: The gene-model audit assistant states a finding in words only; give it tools that draw the evidence behind a finding (a gene track with the annotated model, the RNA junctions and the corrected model, a sequence panel around a frameshift, a table of findings by cause) and show them in the conversation and in an exported report. The strategy-building assistant does not get these tools.
tags: [audit, figures, export, veupathdb-mcp]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: proposed
---

# An audit finding is shown with its evidence

## What happens

An audit run stores its findings, their evidence rows and the reviews, and the audit
assistant describes them in prose. A reader cannot see the evidence: which intron carries
no read, which junctions replace it, where the frame changes. A curator has to open the
site's genome browser and find each case by hand.

The evidence is already in what the sites serve. Each figure below was drawn by hand once,
from browser tracks and gene reports only:

- a gene track: the annotated coding model, the RNA junctions over it with their read
  counts, and the model those junctions imply;
- a sequence panel: the bases around a frameshift in the strain and in its reference, with
  the run that changed;
- a protein length comparison: the model against its orthologs or its reference strain;
- a table of findings by cause and by genome.

## Change

1. In `veupathdb-mcp`, a function per figure kind that takes a finding's stored evidence
   and returns a typed figure specification (tracks, spans, labels, values), read only from
   what the site serves. No drawing in the library.
2. In PathFinder, a data part for each specification and a renderer in the conversation, and
   the same figures in the audit report export.
3. The audit assistant's toolset gains a tool that attaches the figure for a finding. Only
   the audit assistant registers it; the strategy-building assistant's toolsets do not
   change.
4. Tests on recorded evidence: the figure for a missing exon names the zero-read intron and
   the junctions that replace it; the figure for a frameshift names the run and both
   lengths.

## Done when

An audit reply about a finding shows its gene track or sequence panel in the conversation,
the exported report contains the same figure, and the strategy-building assistant's
toolsets are unchanged.
