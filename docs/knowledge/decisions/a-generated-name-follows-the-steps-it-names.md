---
type: Decision
title: A generated strategy name follows the steps it names
description: The strategy row records whether the thread's name is generated and which steps it covers; the turn end generates the name anew from the steps left when a covered step is gone or a value the name states moved, and never touches a name a person chose. Renaming on every edit and never renaming were rejected.
tags: [naming, strategy-graph, persistence]
generated: { by: claude-code/opus-5, at: 2026-10-04T00:00:00Z }
status: stable
---

# What was decided

**The strategy row records where the name came from.**
`conversation_strategies.generated_name_steps` is null when a person chose the
thread's name. A list means the name is generated, and the list holds the steps
it covers: every step of the strategy but a combine
(`domain/strategy/generated_name.py::named_steps`). Every write through
`services/strategies/naming.py::name_the_thread` states the origin in
`generated_over`. `name_if_unnamed` records the steps when it writes the first
title; `rename_strategy_everywhere` (the sidebar rename and the agent's
`rename_strategy`) and `name_the_thread_as_the_graph` (`UpdateStrategyMetaOp`)
clear the record. A write of the record alone appends no strategy snapshot,
because it is not strategy state.

**The turn end keeps a generated name true.**
`ai/conversation/turn_title.py::write_turn_name` writes the first title, or,
when the turn wrote none, calls
`services/conversations/turns.py::rename_if_edits_outdated_it` with the strategy
the turn opened on (`turn_start_strategy`). A generated name is outdated when a
step it covers is gone, or when a covered step no longer holds a value the name
states as a whole word, in any case; a multi-pick value counts each term it
dropped (`name_outdated`). The new name comes from the title model, seeded by
`name_seed`: the organisms the catalog marks for the result, then the criterion
text of each step left (its label when it has none). The turn's message never
seeds it, because for an edit it is the edit instruction. The name is written
through `name_the_thread` under the thread's strategy lock, only while the
record is the one the check read, so a rename by a person during the title call
wins. `put_the_name_on_wdk` then sends it to WDK, the turn writes it as
`data-conversation-title`, and the record takes the steps the strategy holds.
The check and the title call share the 15 s ceiling of the first title
(`TITLE_WAIT_SECONDS`).

**A name written before any step covers the first build.** The `/begin` title,
or the title of a first turn that only asked a question, is a generated name
over no steps. The first turn end that finds steps records them, with no title
call. A strategy that loses every step keeps its name and records no steps, so
the next build is covered again.

No title call is made unless a covered step is gone or a stated value moved.

# Gaps accepted

- A canvas edit outside a turn does not regenerate the name when it lands. A
  covered step it deleted is found at the end of the next turn, because that
  check reads the record; a value it moved is not, because that check compares
  the start and the end of the turn.
- A branch or a copy of a thread carries no record, so its name ("X (branch)",
  "Copy of X") is never generated anew.
- A moved value counts only when the name states its stored form whole. A name
  that says "Chromosome 1" is outdated by a move off "1" and not by a move off
  "01"; an organism term with a strain is not stated by a name that gives the
  species alone.

# What was rejected

**Rename on every edit.** A researcher's own edits churn the name, and each one
costs a title call.

**Never rename.** The name states a filter the strategy no longer applies, and
it travels to WDK and to the gene set the thread imported.

**Reading a deleted step from the turn's start and end alone.** A covered step a
canvas edit deleted stays in the record for good under that rule, so the name is
never generated anew; reading the record finds the step at the next turn end.
