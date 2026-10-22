---
type: Decision
title: An all over many genomes is asked unless the request names genomes
description: A FRAME pass that binds a phyletic expression with presence in every one of three or more genomes is sent back, at most twice, to ask which presence the researcher means, offering only the readings that differ from every genome, unless the researcher's messages name genomes, strains, isolates or proteomes or the criterion holds an accepted reading; when no other reading differs, nothing is asked, and absence and single copy bind as written. Always asking, a prompt rule alone, asking about absence and approximate single copy were rejected.
tags: [agents, frame, orthomcl, parameters]
generated: { by: claude-code/opus-5.5, at: 2026-10-22T00:00:00Z }
status: stable
---

# What was decided

On OrthoMCL a T count counts genomes, and the strains of one species are
several genomes. "Present in all of" a list L of N genomes, written `L=NT`,
asks for every strain, which may be stricter than the researcher means. Two
other presence readings are written from the parameter's help: at least 90
percent of the genomes (`L>=ceil(0.9N)T`), and every species present in at
least half its genomes.

**The question is asked only when the readings differ.** For N of at least 3,
it is raised when `ceil(0.9N)` is below N or a species of the list holds two
or more genomes. Each offered reading differs from every genome: the share
only when `ceil(0.9N) < N`, the species reading only when a species holds two
or more genomes. A list of up to nine genomes of single-genome species asks
nothing, because every reading selects the same groups. All the lists one
criterion asks about share one question, each reading applied to every list.

**The request decides it when it names genomes.** A message with the word
genome, strain, isolate or proteome, singular or plural, has stated the
reading. A word joined by a hyphen, such as "genome-wide", names no genome.
A criterion that holds an accepted reading is not asked again.

**Absence and single copy are never asked.** `L=0T` is absence from every
genome under every reading, and single copy (`L=NT AND L=N`) has no share or
species form.

The rule lives in `domain/strategy/every_genome.py`; FRAME's output validator
`hold_an_every_genome_presence_to_a_question` (`ai/agents/frame_result_checks.py`)
applies it up to [the refusal bound](an-output-check-refuses-at-most-twice-and-never-on-the-last-answer.md) and reads the site's taxonomy only for a draft that
binds `phyletic_expression`.

# What was rejected

- **Always asking.** A request that says "every genome" or "every strain"
  has stated the reading, and a question whose readings coincide costs a turn
  of identical counts.
- **A prompt rule alone.** FRAME binds the shortest writing of "all" without
  a check that holds it to the question.
- **Asking about absence.** `L=0T` means absent from every genome of the
  list under every reading; it has nothing to choose between.
- **Approximate single copy.** One protein in every genome has no share or
  species form in the help's recipes, so `L=NT AND L=N` binds as written and
  FRAME's summary says it may return few groups.

# What would prove this wrong

`tests/unit/domain/strategy/test_an_all_over_many_genomes_is_asked.py` and
`tests/unit/ai/agents/test_frame_asks_about_every_genome.py`, both on the
client's recorded QA taxonomy.
