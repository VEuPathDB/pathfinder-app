---
type: Decision
title: A conversation is a thread; its strategy is an attachment
description: The WDK strategy projection moved off conversations into a 1:1 conversation_strategies side table keyed and cascaded by conversation_id, with no owner column of its own, absent-row-means-never-built semantics and one join the caller asks for; keeping one table with nullable strategy columns was rejected.
tags: [persistence, tenancy, assistant-core, wdk, migration]
generated: { by: claude-code/opus-5, at: 2026-08-21T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-21T00:00:00Z }
status: stable
---

# What was decided

`conversations` was a chat thread and a WDK strategy in one row. A second
assistant on the same runtime has threads and has no strategies, so the row
could not be shared.

**The thread keeps its own state; the strategy is a child row.**
`conversations` holds `id`, `user_id`, `application_id`, `site_id`, `name`,
`dismissed_at`, `parent_conversation_id`, `parent_message_id` and the two
timestamps. `conversation_strategies` holds `record_type`, `wdk_strategy_id`,
`is_saved`, `step_count`, `strategy_ast`, `estimated_size`, `gene_set_id`,
`gene_set_auto_imported`, `experiment_id` and `imported_saved_strategy_ids`.
`conversation_id` is both its primary key and a `ForeignKey(... ondelete=
"CASCADE")`, so the relation is 1:1 by construction and a deleted thread
cannot leave an orphan.

**The dividing question is what the column mirrors.** A column that mirrors
WDK strategy state, or the artifact PathFinder built, moves. A column about
the chat itself stays. That decides the four cases where either answer looked
defensible: `is_saved` mirrors WDK's `isSaved` on the strategy and moves;
`record_type` mirrors `recordClassName` and moves; `imported_saved_strategy_ids`
names WDK strategies the built tree embeds and moves; `dismissed_at` hides the
**chat** from the sidebar and stays, as do the two `parent_*` columns, which
record where a thread was branched from and are anchored on a message.
`site_id` stays: it exists before any strategy does and it scopes every
listing. `experiment_id` moves, because an experiment is PathFinder science
and means nothing to a thread-only assistant.

**The child carries no owner of its own.** No `user_id`, no `application_id`.
Ownership is the parent's `(user_id, application_id)` pair
([tenancy](application-id-tenancy.md)), the ownership helpers are the
runtime's (`assistant_core.conversation.authz`), and every query that touches
the side table drives from `conversations` and inherits its predicates. A
child with its own application column would be a second, silently divergent
answer to who owns the row.

**No row means the strategy was never built.** A thread starts with no side
row; the first strategy write creates one. Readers never branch on the row
being absent: `strategy_view_of` returns a frozen `ConversationStrategyView`
whose field defaults *are* the absent-row semantics (`wdk_strategy_id=None`,
`is_saved=False`, `step_count=0`, `strategy_ast={}`), so every caller reads
the same shape it read from the old columns. The typed row itself
(`ConversationStrategy | None`) stays available for the writers that must tell
"absent" from "empty", and the fork path is the one that does.

**One join, asked for by name.** `conversations` belongs to the runtime
package ([the runtime is a package](the-runtime-is-a-package.md)), so the
thread declares no relationship to the science. A caller that wants both says
so: `ConversationRepository.get_with_strategy` and the two listings select the
thread beside its projection through one outer join (with `populate_existing`,
because the strategy is written by Core statements that do not synchronize a
loaded instance), and `get_strategy` reads the projection alone.
`list_consumers_of_saved_strategy` joins without selecting it, because its
caller reads names. Nothing loads behind the caller's back.

**Clearing is not writing.** `ConversationRepository.clear_strategy` blanks
`strategy_ast`, `wdk_strategy_id` and `step_count` with an `UPDATE`, so a
thread that never built anything stays row-less, and the gene-set and
experiment links survive a cleared graph. This deleted `ConversationUpdate.
strategy_ast_set`, whose only caller wrote SQL `NULL` into a `NOT NULL` column
and got a JSON `null` through SQLAlchemy's `none_as_null=False`; the migration
normalizes those stored `null`s to `{}`.

# What was rejected

**One table with nullable strategy columns and a discriminator.** It is the
smaller diff and it keeps every read one row. It was rejected because the
columns are the problem, not their values: a second assistant's threads would
still carry `wdk_strategy_id`, `strategy_ast` and two foreign keys into
PathFinder's science tables, its migrations would still be PathFinder's
migrations, and the unique index on `wdk_strategy_id` would still be part of
the thread table's contract. The batch exists to make the strategy a
product-owned attachment, and a nullable column is not an attachment.

**An `application_id` on the side table.** Rejected under the rule above: the
child is reachable only through its parent, so a second owner column can only
disagree with the first.

# What would falsify this

`apps/api/src/pathfinder/tests/unit/persistence/test_conversation_strategy_seam.py`
fails the moment a strategy column returns to `Conversation`, an owner column
appears on `ConversationStrategy`, or the thread declares a relationship to
the science again.
`.../tests/integration/persistence/test_conversation_strategy_rows.py` and
`.../test_conversation_strategy_migration.py` fail if the absent-row read, the
first-write insert, the cascade, the unique index, or either direction of
alembic revision `2026_08_21_0002` stops holding.
