---
type: Decision
title: A required genome list is asked from its counts, and at least one builds one MINUS
description: A settled phylogenetic profile that requires two genomes or more asks one card when its at-least-one count differs from its bound count, decided from the bound values alone; the answer is a binding, and at least one builds left MINUS right. One step per genome, a phyletic expression, a typed reading FRAME chooses under a prompt rule and reading the request's words were rejected.
tags: [orthology, phyletic, frame, parameters, reading]
generated: { by: claude-code/opus-5.5, at: 2026-11-04T00:00:00Z }
status: stable
---

# What was decided

`included_species` on `GenesByOrthologPattern` requires every listed genome: the
census pattern marks each one `Y`. A site's tree often has no node for a group, so a
list of genomes can mean each of them or any of them, and the search has one form.

The FRAME output check `hold_an_unsettled_pick_to_a_question`
(`ai/agents/frame_pick_checks.py`) adds one question when a settled criterion of that
search requires two genomes or more and its `any_strain` measurement differs from its
bound count (`domain/strategy/genome_questions.py`). The check reads the bound values
and the measurements `services/strategies/species_readings.py` already records. Equal
counts ask nothing, because the two readings are one set. A count not read within the
measurement budget or under the slow-search guard still asks, and that option states
no number. A value the measurements did not read, such as one the researcher wrote out
as genome codes, asks nothing. The group is every genome the criterion requires.

The question offers two `ReadGenomes` options, and neither is recommended: "At least
one of 61 genomes (1,259 genes)" and "All 61 genomes (501 genes)". The strict binding
stays in place while the card waits. FRAME's prompt, tools and output schema do not
change: the options ride `SlotQuestion.typed_options`, which is omitted from the input
schema.

An answer is a binding with no model in between
([a card option is a binding](a-card-option-is-a-binding.md)). Each answer sets
`Criterion.genome_group`, which settles the question: a criterion that holds one is
not asked again. "All" changes nothing else. "At least one" builds `left MINUS right`:
left is the criterion with the group's codes removed, which keeps its other required
genomes and its exclusions; right is left with the group's codes also excluded, and
names left in `absence_of`. A census holds each genome present or absent, so left minus
right is what the `any_strain` count measures.

The steps are derived from the criterion (`domain/strategy/genome_group_steps.py`), so
the fold derives them again on each build and edit, and an edit of an exclusion updates
both steps and adds none. A rebind keeps the reading while the values still require the
group's genomes or are the values the criterion held. An edit that gives up the reading
deletes the right. A replay keeps a reading its steps still state; when an outside change
moves a step, the reading retires, its strain measurements go, and both steps stay as
plain steps.

The facts part states the reading built and the other reading's count when known, on
the `included_species` row. A settled reading is no assumed value, so no caveat widens
it.

# What was rejected

**One step per genome.** A union of 61 profile steps is 61 requests for one question and
61 rows for a reader, with no answer the two-step form does not give.

**A phyletic expression.** Only OrthoMCL serves the expression parameter, so a genomics
site cannot run it.

**A typed reading FRAME chooses under a prompt rule.** A tool argument and a prompt
paragraph on the reading changed FRAME's tool choices and broke strict and one-genome
questions. A check after the pass holds the same decision and leaves FRAME as it was.

**Reading the request's words.** Text matching on a group name or a phrase cannot tell
which reading was meant, and it fails on each site's own names. The two counts are the
only evidence that the reading changes the answer, and the researcher decides.
