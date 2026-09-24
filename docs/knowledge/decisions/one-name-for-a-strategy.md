---
type: Decision
title: A strategy has one name, and the thread holds it
description: The conversation's name is the strategy's name. The stored AST, the WDK strategy and the gene set auto-import made carry copies, and every rename goes through one service function that writes all of them. A combine no researcher named carries its operator's label. Keeping the AST name authoritative was rejected because it froze the placeholder the first build wrote.
tags: [strategy-graph, naming, wdk, gene-sets]
generated: { by: claude-code/opus-5, at: 2026-09-23T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-23T00:00:00Z }
status: stable
---

# What was decided

**The thread's name is the strategy's name.** `build_strategy_session` names the
graph from the conversation first and falls back to the stored AST name only for
a thread that has none. The AST carries a copy, WDK holds a copy, and the gene
set auto-import made for the thread carries a copy until someone names the set.

**One module renames.** `services/strategies/naming.py::name_the_thread` writes
the conversation (the store may add a suffix to keep it unique, and every copy
takes the stored name), the AST and the auto-imported set, and
`put_the_name_on_wdk` then sends the stored name to WDK.
`rename_strategy_everywhere` does both for a sidebar rename
(`ConversationService.update`) and the agent's `rename_strategy`; the first
title (`name_conversation_if_unnamed`, from the turn and from `/begin`) does the
same through `name_if_unnamed`. A graph edit that renames (`UpdateStrategyMetaOp`) writes the thread
through `name_the_thread_as_the_graph`, and its push sends the name to WDK.

**WDK is written after the lock.** The thread's strategy lock covers the
local writes only; the WDK rename runs after it is released, bounded at 10 s,
and never raises, so a slow site cannot hold the lock or a turn's `finish`.

**WDK is reconciled, not trusted.** A refused WDK rename is logged. The read
before every push records the name WDK holds on `WDKSyncState.wdk_strategy_name`,
and a push whose tree did not move sends the name alone when WDK lags. A turn
that ends on a thread whose stored AST carries another name puts the thread's
name back on the AST and on WDK. An import from WDK names only a thread that has
no name, and a branch pushes its strategy under the branch thread's name.

**A build does not name the strategy.** `build_strategy_from_spec` takes no name,
so neither the spec's hydrated title nor the execution agent can give the
strategy a name the thread does not hold. Until the title lands, a push names a
graph that has no name after the request the thread answers
(`state.domain.original_request`, the text `framing_goal` starts from; the
turn's prompt only when the thread holds none), cut by
`naming.provisional_strategy_name`, and the title replaces that name. The web's
`provisionalName` cuts the thread's first message by the same rule: 60 code
points, one stated set of space characters, and
`packages/spec/provisional_name_parity.json` holds the cases both suites assert.

**A combine is named by its operator.** WDK names a step it receives without a
name after its search, so an unnamed combine read as
`boolean_question_TranscriptRecordClasses_TranscriptRecordClass` on the site.
Every combine PathFinder builds carries `combine_display_name(operator)`, the
push sends it, an operator change renames a combine no researcher named, and a
commit names any combine that carries no name of its own, so a combine pushed
before the rule takes a name patch on the next edit. A name of the form
"<OPERATOR> combine", which the canvas once gave the combines it created, is a
generated name and is replaced the same way. The labels are the canvas
labels; `packages/spec/operations_parity.json` `combine_labels` holds them and
both suites assert them. The site read keeps no name that equals the step's
search name.

# What was rejected

**The AST name as the authority.** The first build ran before the title existed,
so it wrote the conversation's placeholder into the AST and onto WDK. The loader
read the AST name first, so the placeholder won over every later title, and
opening the strategy by id wrote it back onto the conversation.

**A stored column for the name WDK holds.** The read before a push already
fetches the strategy, so the name WDK holds is known when the push needs it;
a column would be one more copy to keep true.
