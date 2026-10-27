---
type: Decision
title: An all over many genomes is asked unless the request names genomes
description: A FRAME pass that binds a phyletic expression with presence in every one of three or more genomes is sent back, at most twice, to ask which presence the researcher means, offering only the readings that differ from every genome, unless the researcher's messages name genomes, strains, isolates or proteomes or the criterion holds an accepted reading; when no other reading differs, nothing is asked, and absence and single copy bind as written. A taxon the expression spans needs a scope FRAME states, whole or named; a whole taxon is held to every genome and its per-species or per-genome writing reaches the same question. Always asking, a prompt rule alone, asking about absence, reading the scope from the request's words and approximate single copy were rejected.
tags: [agents, frame, orthomcl, parameters]
generated: { by: claude-code/opus-5.5, at: 2026-10-22T00:00:00Z }
status: superseded
---

> Superseded by [a refusal rests on typed state](a-refusal-rests-on-typed-state.md): the every-genome question was removed.

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

**A taxon the expression spans has a stated scope.** When the presence units of
a phyletic expression name leaf genomes of two or more species of one genus, or
two or more genomes of one species, FRAME states a scope for that genus or
species in `FrameResult.group_scopes`: `whole` (with optional `except_codes`)
when the request means every genome of the taxon, or `named` when it means
exactly the units written. The taxon is a clade's code, as the expression
writes it, or the full name of a genus, species or clade that names exactly one
taxon; a genus or a species has no code. A scope over a wider taxon (a clade)
covers a narrower one. The trigger reads only the expression and the site's taxonomy,
never the request's words. A pass with an unscoped taxon is sent back to state
one, and at the refusal bound binds with a `group_scope_missing` gap. For a
`whole` scope, every genome of the taxon except `except_codes` must be named
by some unit, present or absent, an accepted reading included, or FRAME is
sent back with the codes it leaves out (the first 12, then a count); at the
bound the pass binds with those codes as a `group_genomes_left_out` gap. A unit that
only writes absence (`L=0T`) triggers nothing, because absence reads the same
under either scope. Every `except_codes` entry must be a genome of the taxon,
or the pass is sent back with the taxon's genome codes. The thread keeps the
scopes across passes, as it keeps record-type roles, and a new request clears
them. A held scope applies only while the pass's presence units still span
its taxon, so a narrowed follow-up is held to the narrower taxon's scope, and a
pass whose presence units fall to one genome of the taxon is held to no scope; a
held `whole` scope that still applies is sent back as stated by an earlier
pass, with restating it named or with `except_codes` offered. A scope stated
under another spelling of the same taxon (code or name) replaces the held one. An expression that writes a `whole` taxon as two or
more AND-joined presence units, per species or per genome, that together hold
every genome reaches the same question as `L=NT`.

The rules live in `domain/strategy/every_genome.py` and
`domain/strategy/named_groups.py`; FRAME's output validators
`hold_the_taxa_to_their_scope` and
`hold_an_every_genome_presence_to_a_question`
(`ai/agents/frame_expression_checks.py`) apply them up to [the refusal bound](an-output-check-refuses-at-most-twice-and-never-on-the-last-answer.md) and read the site's taxonomy only for a draft that
binds `phyletic_expression`.

# What was rejected

- **Always asking.** A request that says "every genome" or "every strain"
  has stated the reading, and a question whose readings coincide costs a turn
  of identical counts.
- **A prompt rule alone.** FRAME binds the shortest writing of "all" without
  a check that holds it to the question.
- **Asking about absence.** `L=0T` means absent from every genome of the
  list under every reading; it has nothing to choose between.
- **Reading the scope from the request's words.** A word rule found the
  group a request quantifies over ("all", "every", "each", "across" before a
  taxon), with exceptions, narrowing follow-ups, abbreviations and head nouns.
  Four review rounds each found a wording that reopened the defect or sent a
  correct expression back: a narrowed follow-up, a bare later mention, a head
  noun the rule did not list, and a strain or a singular record noun read as
  the whole species. FRAME reads the request; the check holds what FRAME
  states against what the expression writes.
- **Approximate single copy.** One protein in every genome has no share or
  species form in the help's recipes, so `L=NT AND L=N` binds as written and
  FRAME's summary says it may return few groups.

# What would prove this wrong

`tests/unit/domain/strategy/test_an_all_over_many_genomes_is_asked.py`,
`tests/unit/domain/strategy/test_an_expression_over_a_taxon_needs_a_stated_scope.py`,
`tests/unit/domain/strategy/test_a_named_group_written_unit_by_unit_is_asked.py`,
`tests/unit/ai/agents/test_frame_asks_about_every_genome.py` and
`tests/unit/ai/agents/test_frame_holds_a_taxon_to_its_stated_scope.py`, all on the
client's recorded QA taxonomy.
