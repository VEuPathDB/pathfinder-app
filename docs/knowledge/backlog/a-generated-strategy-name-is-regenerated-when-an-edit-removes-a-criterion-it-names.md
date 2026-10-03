---
type: Backlog
title: A generated strategy name is regenerated when an edit removes a criterion it names
description: The thread's generated title stays on the strategy after an edit deletes the criterion it named or changes a value it spells out; a nullable marker on the strategy row records that the name is generated and which steps it was written over, and the turn end regenerates it when one of those steps is gone, never touching a name the researcher gave.
tags: [naming, strategy-graph, persistence]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# A generated strategy name is regenerated when an edit removes a criterion it names

**What I did.** On a Naegleria fowleri thread, built peptidase genes with
signal peptides, then deleted the peptidase step (`delete_step`).

**What I got.** The strategy (WDK 214627750) kept the name "Naegleria fowleri
Peptidase Genes With Signal Peptides", with `GenesWithSignalPeptide` as its
only step.

**Why that's wrong.** The saved strategy is named for a filter it no longer
applies, and the name travels to WDK and to the auto-imported gene set.

The same holds for a value edit: a fungidb strategy (WDK 330879483) named
"Fusarium graminearum P450 Genes on Chromosome 1" kept that name after
`set_criterion` moved `GenesByLocation` to chromosome 2 (3,755 genes, result 39).

**Why it happens.** By [one-name-for-a-strategy](../decisions/one-name-for-a-strategy.md)
the thread's name is the strategy's. That name is the generated title of the
first request, written by `services/strategies/naming.py::name_if_unnamed`,
and nothing re-derives a generated name after an edit. Nothing records
whether a name is generated or the researcher's, or what it was generated over.

**Constraints found.**
- The name lives on assistant_core's `Conversation` and its copy on
  veupathdb's `StrategyAst`; both are library models. The only PathFinder row
  is `conversation_strategies`, which exists only after the first strategy
  write, while the title often lands before it.
- The title model (`ai/conversation/title_generator.py::charged_conversation_title`)
  is in `ai/`; `services/strategies/commit.py`, where edits land, cannot import
  `ai/` under the layering contracts.
- The title task each turn starts is seeded with that turn's message, which
  for this case is the delete instruction, so it cannot be the new seed.

**Fix.**
- Marker: a nullable column `conversation_strategies.generated_name_steps
  jsonb`, added by a new alembic revision, carried on `ConversationStrategy`,
  `ConversationStrategyView` and `ConversationUpdate`. None means the name is
  the researcher's; a list means the name is generated and holds the step ids
  the strategy had when the name was written. A write that sets it upserts the
  row; a row with defaults reads as an absent one.
- Who sets it: `name_if_unnamed` when it writes the generated title.
- Who clears it: `rename_strategy_everywhere` (the sidebar rename and the
  agent's `rename_strategy`) and `name_the_thread_as_the_graph`
  (`UpdateStrategyMetaOp`), since both carry a name a person chose.
- Trigger: at turn end in `ai/conversation/turn_runner.py`. When the marker is
  a list and the turn removed one of its steps or changed a value the name
  spells out (compare the turn-start
  revision, `services/conversations/turns.py::turn_start_revision_id`, with the
  current strategy), generate a title seeded with the remaining criteria's
  texts and write it through `naming.name_the_thread`, then
  `put_the_name_on_wdk`. The marker takes the current step ids.
- Gap: a canvas delete outside a turn does not regenerate the name, unless
  `commit.py` also takes an injected title port.
- When the work lands, record a decision beside
  `one-name-for-a-strategy.md` naming the two rejected alternatives: rename on
  every edit (a researcher's own edits churn the name and each costs a title
  call), and never rename (the name states a filter the strategy no longer
  applies).

**What you'd get.** "Naegleria fowleri Genes With Signal Peptides" after the
delete, and a name the researcher gave stays as given.
