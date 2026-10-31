---
type: Backlog
title: A short model names the frameshift that cut it
description: The length check calls a short model a truncated annotation whenever the genome encodes the missing part on the same strand, without asking in which reading frame; when the missing part continues in another frame, the check must find the base where the frame changes, say whether it sits in a homopolymer or a short repeat, and compare that run with the same gene in the closest strains.
tags: [audit, length, frameshift, assembly, veupathdb-mcp]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: proposed
---

# A short model names the frameshift that cut it

## What happens

`veupathdb_mcp.audit.windows.confirm_in_dna` translates the window in six
frames and joins the three frames of the gene's strand into one string before
it matches each reference window. A window found anywhere on that strand is
`genome_same_strand`, and `audit.length._short` returns `GENOME_ENCODES` from
those counts. PathFinder's `domain/audit/findings.py::_length` then names a
`truncated_model` at high certainty, and the run's synthesis calls it an
annotation truncation.

That reading is wrong when the missing part sits in another frame. The gene
model follows the assembly faithfully, and the stop comes from an insertion or
deletion in the assembly. The usual place is a homopolymer or a short tandem
repeat, where long-read assemblies miscount bases.

Example: PfNF54_040013300 on PlasmoDB (556 aa; 58 orthologs of 1,369 to 2,031
aa; PF3D7_0407700 is 1,629 aa). The two proteins are identical for 527
residues. Then the NF54 assembly has 29 A in a run where 3D7 has 28, and the
rest of the 3D7 protein translates from the NF54 DNA one frame over. The
contig is 1.2 Mb, the gene is 380 kb from its nearer end, and the window holds
no N. 3D7 was cloned from NF54, so a one-base difference in a 28-base run is
far more likely an assembly error than a mutation. The check reported an
annotation truncation instead.

## Change

1. In `confirm_in_dna`, record the frame of each `genome_same_strand` and
   `model` window, not only the strand.
2. In `check_length`, when the matched windows change frame, locate the change
   between the last window of one frame and the first window of the next.
   Read the DNA there for the longest homopolymer or tandem repeat, and give
   its position and length.
3. Add a verdict for this case, `FRAMESHIFT`, that names the position, the run
   and the frame change.
4. For a strain genome, read the same run in the gene of the reference strain
   the strain check already names. Report both counts so that a one-base
   difference between near-identical genomes is visible.
5. Release veupathdb-mcp and take the pin.
6. In PathFinder, `_length` maps `FRAMESHIFT` to its own error type, a
   frameshift in the assembly, with words that say the model follows the
   assembly and the assembly likely miscounts the run.
7. Tests: a recorded window with a one-base insertion in a poly-A run gives
   `FRAMESHIFT` at that run. A clean truncation with no frame change still
   gives `GENOME_ENCODES`.

## Done when

A rerun of the NF54 audit reports PfNF54_040013300 as a frameshift at the
poly-A run, with 29 A in NF54 against 28 in 3D7, and not as an annotation
truncation.
