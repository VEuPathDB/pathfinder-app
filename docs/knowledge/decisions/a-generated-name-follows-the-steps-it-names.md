---
type: Decision
title: A generated name follows the seed it was written over
description: A generated strategy name records its seed, the wire value of each parameter of each step it covers, and is generated anew when a seed step is gone or a seed value moved; a step name PathFinder made records the search and the labels it was made from, and is made again when a value moves. A name a person wrote is never rewritten. Reading the name's words against the wire values, renaming on every edit and never renaming were rejected.
tags: [naming, strategy-graph, persistence]
generated: { by: claude-code/opus-5.5, at: 2026-11-03T00:00:00Z }
status: stable
---

# What was decided

**The strategy row records where the name came from.**
`conversation_strategies.generated_name_seed` is null when a person chose the
thread's name. A map means the name is generated, and the map is its seed: for
every step of the strategy but a combine, the wire value of each parameter
(`domain/strategy/generated_name.py::name_seed`). Every write through
`services/strategies/naming.py::name_the_thread` states the origin in
`generated_over`. `name_if_unnamed` records the seed when it writes the first
title; `rename_strategy_everywhere` (the sidebar rename, an imported saved
strategy's own name and the agent's `rename_strategy`) and
`name_the_thread_as_the_graph` (`UpdateStrategyMetaOp`) clear it. A write of the
seed alone appends no strategy snapshot, because it is not strategy state.

**The turn end keeps a generated name true.**
`ai/conversation/turn_title.py::write_turn_name` writes the first title, or,
when the turn wrote none, calls
`services/conversations/turns.py::rename_if_edits_outdated_it`. A generated
name is outdated exactly when a seed step is gone or holds another wire value
than its seed for a seed parameter (`name_outdated`). A step or a parameter
added beside the seed does not outdate it. The check compares the stored seed
with the stored strategy, so an edit made on the canvas between turns counts at
the next turn end. The new name comes from the title model, given
`title_text`: the organisms the catalog marks for the result, then the
criterion text of each step left (its label when it has none). The turn's
message is never that text, because for an edit it is the edit instruction. The
name is written through `name_the_thread` under the thread's strategy lock,
only while the seed is the one the check read, so a rename by a person during
the title call wins. `put_the_name_on_wdk` then sends it to WDK, the turn
writes it as `data-conversation-title`, and the row takes the seed of the
strategy it now holds. The check and the title call share the 15 s ceiling of
the first title (`TITLE_WAIT_SECONDS`).

**A name written before any step covers the first build.** The `/begin` title,
or the title of a first turn that only asked a question, is a generated name
over an empty seed. The first turn end that finds steps records their seed,
with no title call. A strategy that loses every step keeps its name and records
an empty seed, so the next build is covered again.

**A step name PathFinder made follows the values it labels.** A criterion
titles its step by the search's display name and the site's vocabulary labels
of the values it binds, which the binding pass reads
(`step_naming.criterion_title`; `domain/strategy/step_naming.py::StepTitle`). A label
counts when the value is shown, is not the site's initial value or prompt, and
is not the organism parameter, which the strategy name carries; the labels are
cut on a word at 60 code points. For a pair the search declares in
`radio-params` (`Criterion.radio_pairs`, read from the search's properties when
FRAME binds it, when a strategy is read back and when a controls run offers
it), a vocabulary half bound to `N/A` has no label and the free-text half
is labelled by its own value, so `ec_wildcard=*` beside `ec_number_pattern=N/A`
titles the step "EC Number: *". `StepWords.titles` stores that title per step
id in the strategy's metadata. A step whose name equals its stored title is
PathFinder's: `StrategyGraph.note_words` gives it the newer title, and a
parameter write (`_apply_update_params`) gives it its own title less the label
of every value it no longer holds (`StepTitle.kept`). A step whose name is not
its stored title, because a person renamed it, a model wrote it, the site holds
another, or it was stored with no title, keeps its name. A rebound search keeps
a researcher's name too.

**A nested group is named after the steps inside it.** The site draws the
secondary input of a combine as a nested strategy when that input has an input
of its own, and labels it by the `expandedName` of the combine that takes it
(`wdk-client` `StrategyUtils.ts::makeStepBoxDisplayName`, which shows "Unnamed
Nested Strategy" for a combine with none). `combine_naming.py::name_the_combines`
gives every combine whose secondary input is a combine, and that names no saved
strategy, the names of the steps in that group in tree order, cut on a word at
60 code points, after the operator's label when every combine in the group has
one operator. It runs after every build and every commit, so the name follows
the steps. A create or a name write sends it by a PATCH with `expanded` set, so
the site draws the group open and every step in it offers Revise
(`wdk-client` `StepBoxes.tsx`, where a nested box has `allowRevise` false and
`ExpandedSteps` draws the inner steps only when `expanded` is true). A saved
strategy's own name, and a name the site imports with `expanded` set, are kept.

**A lone step takes the secondary side.** When one input of a combine
PathFinder builds is one step and the other has an input of its own, the group
is the primary input and the step the secondary, and the operator mirrors to
keep the question (`domain/strategy/combine_order.py::flat_join`: MINUS becomes
RMINUS, LONLY becomes RONLY). The build (`spec_tree.py`), the restated tree of
an edit (`edit_plan.py`), a combine an edit adds (`spec_to_operations.py`) and
an export's join (`_eda_step_write.py::join_write`) all place their inputs
through it, and a group an edit or an export grows on the secondary side of a
combine over a lone step moves that combine's inputs the same way
(`wired_in_place`). The site then draws the strategy flat. A group stays on the
secondary side only when both inputs are groups, when the operator has no
mirror (COLOCATE), when the input is a saved strategy, or when the combine holds
a filter, whose value names its inputs by side. INTERSECT and UNION return the
same records in either order; measured on QA PlasmoDB, an INTERSECT of a leaf
and a UNION group returned 1551 genes in both orders and a UNION 3951, each
with the same default `gene_boolean_filter_array`.

# Gaps accepted

- A group a researcher collapsed on the site opens again at the next name
  write PathFinder sends for its combine.
- A combine the researcher or the model adds by a graph operation (the canvas,
  `apply_operations`) keeps the order it names.

- A name a person gives a nested group on the site and then collapses is not
  read back, so the next write of that combine sends the generated name.

- A branch or a copy of a thread carries no seed, so its name ("X (branch)",
  "Copy of X") is never generated anew.
- A name stored before its seed or its step title was recorded reads as a
  person's and is never rewritten; the migration `2026_11_03_0001` drops the
  older step list rather than guess wire values for it.
- A value written outside the spec (the canvas, BUILD's `update_leaf_params`)
  takes its label out of a step name, and the next spec pass that binds it puts
  the fresh label back.
- A seed value that moves to an equal reading in another wire form ("01" to
  "1") still generates the name anew.

# What was rejected

**Reading the name's words against the wire values.** A strategy name was
outdated when it carried a moved value as a whole word, and a step name had
each moved value replaced where its words carried it. Both read model-written
text: a name that states a value another way ("Chromosome 1" for "01", a species
for a strain) was missed, and a value the name carried twice or one two
parameters shared could not be placed. The seed and the stored title are typed
and compared for equality.

**Rename on every edit.** A researcher's own edits churn the name, and each one
costs a title call.

**Never rename.** The name states a filter the strategy no longer applies, and
it travels to WDK and to the gene set the thread imported.

**Keep the stated input order and only send groups expanded.** The steps show,
but inside a nested box the researcher can collapse, after which they offer no
Revise again. A flat strategy has no box to collapse.
