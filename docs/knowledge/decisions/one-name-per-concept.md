---
type: Decision
title: One concept has one name, in the app and in what the model is told
description: Every concept a researcher reads about has one name, the lexicon in conventions/vocabulary.md bans its synonyms, and scripts/check-vocabulary.mjs fails a string that uses one. The runtime's package names are not the researcher's vocabulary. Leaving the wording to each feature was rejected because the rail said Scratchpad while the tools said note.
tags: [decision, copy, vocabulary, frontend, agents, gates]
generated: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
status: stable
---

# What was decided

A concept has one name wherever a researcher can read it: panel titles, buttons,
tooltips, empty states, toasts, dialogs, the tool labels a trace row shows, the
`detail` of a refusal, the `/help` text and the export headers. The model is
told the same name in its instructions, its tool descriptions and its retry
messages, because the model repeats what it is told to the researcher.

The names are the rows of [the lexicon](../conventions/vocabulary.md). Where
VEuPathDB owns a concept (strategy, step, search, dataset, study), the name is
the one its sites use. Where two names look alike but name two concepts (notes
and memory, plan and strategy, dataset and study and experiment), the lexicon
says so and both stay.

`node scripts/check-vocabulary.mjs` reads the lexicon and fails on a banned
synonym in a string its scope reads. A `researcher` row reads what a researcher
sees; an `all` row also reads the model's text, because some words (node, leaf,
criterion) are the model's tool contract and stay in the model's text only.
It also fails when a template or a JSX expression puts a raw value into the web
app's copy: an identifier the lexicon's raw values table names, such as
`siteId`, holds an id, and the copy shows its name.

# The runtime's names are not the researcher's words

`assistant_core.scratchpad`, the `scratchpad` routes, the
`data-scratchpad-updated` part kind, the store keys and the test ids keep their
names. They are identifiers, and the runtime package is another repository's
code. The gate never bans an identifier's name, a path or an import, so an internal
name does not have to change for the copy to be right. What the runtime itself
writes for a reader (its tool docstrings, its summaries, the index header the
agent reads) is text, and it follows the lexicon in the runtime's own release.

# Rejected

- **Leaving the wording to each feature.** Each panel chose its own word, so the
  rail said "Scratchpad" while the tools said "Save note" and "Pin note", the
  site menu said "Switch database" while every route said site, and the EDA
  cells said "compute" after the glossary had named it comparison. A glossary
  without a gate had already drifted once.
- **A banned-word row for the site ids.** A site id reaches the copy through an
  interpolation, which no word list sees, and the gate matches in any case, so
  a row banning `plasmodb` also bans PlasmoDB, the name the copy should use.
- **Renaming the internal identifiers with the copy.** The route, the part kind
  and the runtime module are contracts with other code and another repository;
  renaming them changes no string a researcher reads.
- **One ban list for every reader.** The model's structure tools take `leaf` and
  node kinds, and a researcher never reads them. A single list either bans the
  tool contract's own words or lets them reach the screen.

# Where it is enforced

- `scripts/check-vocabulary.mjs` and `scripts/check-vocabulary.test.mjs`, run
  by the `vocabulary` pre-commit hook and the `check-vocabulary` CI job.
- `apps/web/src/vocabulary.test.ts` and
  `apps/api/src/pathfinder/tests/unit/test_user_facing_vocabulary.py` keep the
  internal names (EDA, WDK, FRAME, Lead) off the screen; see
  [the user-facing vocabulary](user-facing-vocabulary.md).
