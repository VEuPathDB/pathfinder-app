---
type: Decision
title: The runtime is a package, so the boundary is an installation fact
description: assistant_core moved out of apps/api into packages/assistant-core with its own pyproject, lock, tests and CI lane, consumed as an editable path dependency; import-linter contract 7 was replaced by the package's dependency list plus its own boundary suite. Keeping the runtime in-repo behind import contracts only was rejected, because the program owner ruled the boundary must be observable and real.
tags: [assistant-core, ws-v, architecture, packaging, import-linter, persistence]
generated: { by: claude-code/opus-5, at: 2026-08-22T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-22T00:00:00Z }
status: stable
---

# What was decided

The assistant runtime is `packages/assistant-core`: its own `pyproject.toml`,
its own lock file, a `src/assistant_core` layout importable with no
`pathfinder.` prefix, its own test tree, and `apps/api` consuming it as an
editable path dependency. A module under
`assistant_core/` cannot import `pathfinder` because the distribution it
belongs to does not depend on it. The boundary stopped being a rule a linter
applies and became a fact about what is installed.

**The pinned external surface moved with it.** The batch-D contract listed
eleven modules the runtime was allowed to reach outside itself, and every one
of them is runtime-owned by nature, so the list is now the package's own
contents:

- `platform/{config,context,db,logging,pydantic_base,types}.py`. `config.py`
  split: `RuntimeSettings` (database URL, engine echo, SSE keep-alive, log
  level and format) is the package's; the product's `Settings` subclasses it
  and installs itself through `use_settings_source`, so one settings instance
  still serves the whole process. `context.py` split by what reads the
  variable: request, user, application, site, stream and operation ids are the
  runtime's; `veupathdb_auth_token_ctx` and `request_base_url_ctx` stayed.
  `db.py` split by what it imports: the engine, the session factory and the
  request-scoped session are the runtime's; `init_db`, which runs alembic
  against `alembic.ini`, is the application's and became
  `platform/migrations.py`. `errors.py` and `principal.py` stayed: their
  taxonomies name WDK, VEuPathDB bearers and PathFinder service tokens.
- `integrations/embeddings/{model,prefixes}.py` became
  `assistant_core/embeddings/`. `semantic_index.py` stayed, because it is
  typed on `WDKSearch`.
- The tables the runtime reads and writes: `conversations`, `messages`,
  `conversation_events`, `memory_tombstones`, plus the declarative `Base`, the
  `GUID` type, the application-id column and `MessagesRepository` /
  `MessageMetadata`. `users`, `conversation_strategies`, `gene_sets`,
  `experiments`, `background_tasks` and the rest stayed.

**One MetaData, two declarative bases would not work, so there is one base.**
A foreign key resolves only inside the `MetaData` that holds both tables, and
the keys cross in both directions: `conversations.user_id` and
`conversation_events.task_id` point at host tables, while
`conversation_strategies`, `background_tasks` and the scratchpad tables point
back at `conversations`. Combining two metadatas in alembic's
`target_metadata` would satisfy autogenerate, which this repository does not
use, and still leave `create_all` unable to emit either constraint. So the
package exports `Base` and the product maps its tables on it. Alembic's
`target_metadata` is unchanged, and every migration stays hand-written.

**The thread lost its relationship to the science.** `Conversation.strategy`
and `Conversation.strategy_view` named `ConversationStrategy`, which is
PathFinder's; a package class cannot. Callers that want both now ask:
`ConversationRepository.get_with_strategy` and the two listings select the
thread beside its projection in one outer join, `get_strategy` reads the
projection alone, and `build_conversation_response` / `build_conversation_summary`
take it as an argument. `Conversation.user` went the same way, but
`User.conversations` stayed as a one-directional relationship: the direction
product-to-package is legal, and without it the unit of work has no reason to
insert a user before the thread that references it.

**An assistant's turn-context factory became async.** PathFinder's factory read
`conversation.strategy_view` from the row the runtime handed it; with the
relationship gone it has to read its own projection, and a synchronous factory
cannot. `TurnContextFactory` is now
`Callable[[TurnContextRequest], Awaitable[TurnContext]]`.

# What was rejected

**Keeping the runtime in `apps/api` behind import contracts only.** It is the
smaller change and contract 7 did bite. It was rejected because the program
owner ruled the boundary must be observable and real: a contract is a promise
a reviewer has to trust, and a package that cannot install its way into the
science is louder than a linter. The rule also only ever held for people
running the gate; the package holds for anyone who installs it.

**Leaving `conversations` product-side.** It is by far the cheaper option: the
strategy relationship and thirty call sites would not have moved. It was
rejected because the thread is the runtime's central row. It carries
`assistant_id`, it is what `messages`, `conversation_events` and every
checkpoint hang off, and a second assistant with no science still needs it. A
runtime whose own event log foreign-keys a table the host owns has not been
extracted, it has been rehoused.

# What replaced contract 7

Contract 7 forbade any chain from `pathfinder.assistant_core` to the science.
The module no longer exists, so the contract cannot be written. Three things
carry its weight:

1. `packages/assistant-core/pyproject.toml` declares no dependency on this
   application. This is the enforcement; the rest is instrumentation.
2. `packages/assistant-core/packages/assistant-core/tests/unit/test_package_boundary.py` walks every
   module in the package and fails on an import naming `pathfinder`. The two
   wire-type modules it once read are now the package's own; see [the runtime's
   part payloads live in the runtime](runtime-part-payloads-live-in-the-runtime.md).
3. A seventh contract still exists in `apps/api`, asserting something that is
   still true in-repo: the science never imports an assistant's composition
   root. An assistant is assembled from `ai/`, `domain/` and `services/`; a
   module in those trees that reaches `pathfinder.assistants` has inverted the
   wiring. It is direct-only, like the six layer contracts, because the chat
   dispatcher still reaches the registry through the job runner - the
   turn-pipeline seam WS3 named and did not close.

# What would falsify this

`cd packages/assistant-core && uv run pytest` runs the package's whole suite
with no `pathfinder` installed; the day it needs one, the boundary is gone.
`apps/api/src/pathfinder/tests/unit/assistant_core/test_core_boundary.py`
fails if the dependency edge reverses or the two source trees merge.
`uv run lint-imports` fails if the science starts importing the composition
root.
