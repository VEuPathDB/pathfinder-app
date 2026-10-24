---
type: Backlog
title: Two site bugs are reported to VEuPathDB
description: OrthoMCL's Single Copy Orthogroups search runs the genome-count query, and WDK answers 500 instead of 422 when a hidden parameter empties a dependent vocabulary; both are VEuPathDB's to fix and are measured on QA.
tags: [upstream, orthomcl, wdk]
status: proposed
---

# What is wrong

## Single Copy Orthogroups is the genome-count search

`OrthoMCLModel/Model/lib/wdk/OrthoMCL/questions/groupQuestions.xml:85` defines
`<question name="GroupsBySingleCopy" queryRef="GroupIds.ByGenomeCount" displayName="Single Copy Orthogroups">`:
the same query as `GroupsByGenomeCount` ("Number of Taxa"), with an empty description and a
`TODO` beside it. Measured on QA OrthoMCL (2026-10-23), both searches with the default ranges
(all 4-20, core 2-10, peripheral 2-10) return 8,699 groups, and the largest "single copy"
group, OG8_0011231, holds 1,255 proteins in 13 taxa. A researcher who picks the search on the
site, or an assistant that trusts its name, gets every group in the taxa range.

PathFinder's search note steers the model off this search, and FRAME builds single copy with
`build_phyletic_expression` as a pattern that holds exactly one protein in each genome
(`each_genome_of` X, `proteins` `exactly` 1); single copy often returns few groups.

## A hidden parameter that empties a dependent vocabulary answers 500

On QA PlasmoDB, `GenesByRNASeqpfal3D7_Bartfai_time_series_rnaSeq_RSRCPercentile` with a valid
`profileset_generic` and the hidden `channel` set to `Channel 2` answers `500 Internal Error`;
the site log shows `WdkEmptyEnumListException: No item returned by the query
[GeneVQ.GenericPercentileSamples] of FlatVocabParam [geneParams.samples_percentile_generic]`.
An invalid `profileset_generic` answers a clean 422 that names the value. The 500 hides which
value is wrong. PathFinder no longer sends a hidden value the website would not send
(veupathdb-mcp 0.2.0b40), so this is reported for WDK's own error contract.

# Change

Report both to VEuPathDB with the evidence above: OrthoMCLModel gives the question a
single-copy query or removes it; WDK answers 422 naming the dependent parameter when a
vocabulary query returns nothing for the values given.

# Done when

Both are filed with VEuPathDB, and this item is removed with a log line naming the issues.
