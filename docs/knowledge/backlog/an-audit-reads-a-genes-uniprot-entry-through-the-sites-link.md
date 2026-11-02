---
type: Backlog
title: An audit reads a gene's UniProt entry through the site's own link
description: The gene-model audit cannot compare a corrected model with an independently determined protein; give it a tool that follows the UniProt identifier the VEuPathDB gene record lists, reads that one entry, and reports which model it matches, with the entry's evidence level and full provenance.
tags: [audit, uniprot, provenance, veupathdb-mcp]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: proposed
---

# An audit reads a gene's UniProt entry through the site's own link

## What happens

When the audit proposes a correction from RNA junctions, the only support it can read is the RNA and
the ortholog models, which come from similar annotation pipelines. A UniProt entry built from an
mRNA, a cDNA or protein sequencing is independent evidence, and VEuPathDB gene records already link
to UniProt.

## Change

1. In `veupathdb-mcp`, a tool that reads the UniProt identifiers from the gene record the site serves,
   fetches only those entries from the UniProt REST service (one request each), and compares each
   entry's sequence with the annotated and the corrected model.
2. It reports, per entry: the accession, the entry version, reviewed or unreviewed, the protein
   existence level, the cross-referenced EMBL records and their molecule type (mRNA, genomic), and
   whether the sequence equals the annotated model, the corrected one, or neither.
3. An entry counts as independent only when it comes from an mRNA, a cDNA or protein sequencing; an
   entry copied from a genome annotation is reported as such and does not count.
4. Every value carries its provenance: the site and gene record it came from, the UniProt accession and
   entry version, and the request time. No identifier is searched for by text; only the site's own link
   is followed.
5. Tests on recorded gene records and recorded UniProt entries.

## Done when

An audit finding for a corrected model names the UniProt entries the site links, says which model each
matches, at what evidence level, and where each value came from.
