---
type: Backlog
title: A gene-model audit runs on the evidence tools
description: A read-only evidence sub-agent ranks the genes whose annotated model disagrees with two or more independent kinds of site evidence, writes an evidence card per gene, and has curators review the top of the list; a retrospective test against past model corrections comes first, and genome-wide scale needs bulk data access rather than per-gene web requests.
tags: [evidence, annotation, sub-agent, scale, wdk, jbrowse]
generated: { by: claude-code/opus-5, at: 2026-10-20T00:00:00Z }
status: proposed
---

# A gene-model audit runs on the evidence tools

**Coming question.** PathFinder stores an audit run unit by unit (`audit_runs`,
`audit_genomes`, `audit_findings`, `audit_evidence`), carries it through collect,
screen, confirm and tie-break in jobs on the `audit` queue, and serves it
at `GET /api/v1/audits` and its findings routes, starts a stored run again at
`POST /api/v1/audits/{run_id}/start`, and lists a researcher's runs on the web's
`/audits` page. The audit assistant plans a run with `plan_gene_model_audit` and
starts it with `start_gene_model_audit` once the researcher approves the card. A
standalone prototype outside this repository measures the tools and the model first.

## The question

Which genes in a reference annotation have a model that two or more independent
kinds of evidence contradict? The output is a ranked list with one evidence card
per gene, and the measure is how many of the top 50 curators confirm. The same
audit applies to every site that holds the evidence.

## Evidence the sites already serve

Measured on QA PlasmoDB on 2026-10-20:

- The `gene` record type holds 75 tables (the `transcript` type holds none). One
  `POST /service/record-types/gene/records` returns, per gene, the exact exon, CDS
  and UTR coordinates (`GeneModelDump`), per-peptide protein coordinates
  (`MassSpecDownload`), modification sites (`MassSpecMod`), structure coverage
  (`PdbSimilarities`, `AlphaFoldLinkouts`), population genetics attributes,
  phenotype tables and per-sample expression (`ExpressionGraphsDataTable`). An
  unknown attribute or table name answers 500, so names are checked against the
  expanded record type first.
- JBrowse serves 1,056 RNA-seq coverage tracks as bigWig and the intron junctions
  as a tabix GFF; the store answers byte-range reads (206), so one gene's region
  is read without the whole file. Long-read models per study and genome-coordinate
  peptides are tabix GFF tracks in the same store; their range reads are not yet
  measured.
- The `dataset` search `DatasetsByGeneList` ranks published gene lists that
  overlap a given set, with fold enrichment and p-value.
- OrthoMCL group records hold member lengths and Pfam positions, which test an
  annotated start against its orthologs.

## Independent kinds of disagreement

An unannotated junction with read support; a long-read isoform whose exon chain
differs from the model; a peptide split across an intron the model lacks; an
N-terminal peptide outside the annotated protein; a protein length that is an
outlier in its ortholog group; a UTR whose coverage stops well inside or past the
annotated end.

Checks that need no RNA data, measured on every QA genome with gene models: a protein length
outlier in its ortholog group, verified against the six-frame translation of the gene region; a
gene missing in one strain of a species, located between conserved neighbours; two neighbouring
genes fused into one model; a strain model that lacks part of its species reference; a pseudogene
call on a gene whose rebuilt CDS is one intact ORF; a selenoprotein model that stops at its Sec
codon; an organelle gene split at the end of a circular genome stored as a linear contig. Each reads
only site-served data (genome reports, gene records, JBrowse range reads of the genome FASTA) and
names its inputs, thresholds and known false positives in the prototype's check list.

## Before a genome-wide run

1. A retrospective test: genes whose models were corrected in past releases are
   ground truth, if the earlier models are recoverable from the sites.
2. Calibration questions with known answers, run on the default model only.
3. A pilot of about 100 genes on QA, paced one request at a time.
4. Genome-wide scale reads evidence in bulk, never one web request per gene: a
   tabular or table report over one search answers every gene in one request,
   coverage files are read whole from where they are stored, and a per-release
   table computed by the data workflows is the end state. Agree the access with
   the VEuPathDB team before any genome-wide run.
5. Curator review of the top of the list.
