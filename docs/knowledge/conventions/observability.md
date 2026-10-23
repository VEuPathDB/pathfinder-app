---
type: Convention
title: What a trace holds, and which Langfuse view answers which question
description: Every chat turn is one OpenTelemetry trace exported over plain OTLP/HTTP to Langfuse, on the conversation's session and the researcher's user; product events and rating scores land on the same project, and the usage devtool reads the same cost from the database.
tags: [observability, langfuse, tracing, cost, operations]
generated: { by: claude-code/opus-5, at: 2026-09-28T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-09-28T00:00:00Z }
status: stable
---

# Where the wiring lives

The runtime owns the tracer (`assistant-platform: packages/assistant-core/src/assistant_core/platform/observability.py`).
`install_observability` reads only the standard OpenTelemetry variables
(`OTEL_EXPORTER_OTLP_ENDPOINT` or `_TRACES_ENDPOINT`, `_HEADERS`, `_PROTOCOL`,
which must be `http/protobuf`, and `_METRICS_ENDPOINT` for metrics, off by
default). With no endpoint it installs nothing. It instruments every pydantic-ai
agent run, both httpx distributions and, where the host passes it, the SQLAlchemy
engine.

PathFinder's `platform/observability.py` calls it once per process: the api as
`pathfinder-api` (with its engine), the worker as `pathfinder-worker`. It adds the
Authorization header Langfuse's ingress reads, built from `LANGFUSE_PUBLIC_KEY`
and `LANGFUSE_SECRET_KEY`. `create_app` instruments the routes through
`trace_routes`, because the middleware stack is built before the lifespan runs;
the server spans record nothing until the lifespan installs a provider. A
request span carries `user.id` once the principal resolves and `app.request_id`.

**A new agent, sub-agent or tool needs no wiring.** Instrumentation is per
process, so a run started anywhere under a turn is a child of that turn's trace.

# What one trace holds

`ai/conversation/turn_runner.py` runs each turn under `traced(...)`, the runtime's
root span. The chat request span in the api is a separate trace: the api never
runs the model. A durable task's body is its own root span, named after its tool,
on the same session.

| Attribute on the root span | Langfuse field | Value |
|---|---|---|
| span name, `langfuse.trace.name` | trace name | the assistant id (`pathfinder`) or the durable tool |
| `session.id`, `langfuse.session.id` | sessionId | the conversation id |
| `user.id`, `langfuse.user.id` | userId | the researcher's user id |
| `langfuse.trace.tags` | tags | the site id; `durable-task` for a task |
| `langfuse.trace.metadata.<key>` | metadata | `assistant_id`, `turn_id`, `site_id`, `turn_kind` (`message` or `durable_completion`), `provider`, `tier`, `model_<role>` |
| `langfuse.trace.input` | input | the researcher's message, only when `OTEL_INCLUDE_CONTENT=true` |
| resource `deployment.environment.name` | environment | `API_ENV` |

Every span under the root carries `session.id` and `user.id` too, so a filter on
either reaches each generation. Beneath the root: the Lead's `invoke_agent` span,
each sub-agent's `invoke_agent` span under the tool call that dispatched it, each
model request (`chat <model>`, with tokens and, when content is on, the prompt and
completion) and each tool call. A priced model request carries
`gen_ai.usage.cost`, the price the runtime charged, so Langfuse shows the cost the
message row records and needs no model price table.

The assistant message's `metadata.traceId` is the turn's trace id, so the id in the
UI opens the trace in Langfuse.

# Which view answers which question

| Question | Where |
|---|---|
| One conversation: every turn, its prompts, its cost | Sessions, then the session named by the conversation id |
| Cost and turns per researcher | Users |
| Cost per day, per model, per trace name | the built-in Dashboards (filter by environment and tag) |
| How testers use the UI | the session's `product.*` events, or Traces filtered by the `product-event` tag |
| What a researcher thought of an answer | the `rating` score (1, -1, 0 when cleared) on the turn's trace |

The product events are `card_answered`, `strategy_opened`, `export_requested`,
`turn_undone`, `assistant_regenerated` and `site_switched`, sent by the web through
`POST /api/v1/product-events`, and `conversation_created`, recorded by the server
when a thread's first message creates it.

# What a log line names

Both processes log JSON lines through the runtime's `setup_logging`, whose stdlib
bridge runs `merge_contextvars` too, so a line from procrastinate, httpx, a library
or pydantic-ai written inside a bound block carries the same keys as PathFinder's
own. The keys are the fields of `platform/log_ids.py::LogIds`, which refuses any
value that is not an id. The bound keys are ids only; no line carries a prompt, a
message, an attachment, an email, a token, a cookie or a key; exception messages
and tracebacks stay as system text.

| Work | Bound at | Keys |
|---|---|---|
| A chat turn | `jobs/impls/chat_turn_impl.py`, and the resolved site at `ai/conversation/turn_runner.py::run_turn` | `conversation_id`, `turn_id`, `user_id`, `site_id`, `assistant_id` |
| A durable body | the runtime's `run_durable_task` | `conversation_id`, `user_id`, `task_id`, `tool_name`, `site_id` |
| A completion turn | the runtime's runner, `site_id` at `run_turn` and `assistant_id` at `jobs/completion.py` | `conversation_id`, `user_id`, `task_id` and `tool_name` of the task that opened it, `site_id`, `assistant_id` |
| An audit job | `services/audit/job.py::carry_run` | `run_id`, `user_id`, `conversation_id`, `site_id` |
| An API request | `transport/http/deps.py::bind_request_log_ids`, an app dependency | `method`, `route` (the template), `conversation_id` from the path |

On an API request PathFinder also sets two runtime context variables the
runtime's processors put on every line: `request_id` in the request middleware
(`main.py`), taken from `X-Request-ID` only when it is at most 64 letters,
digits and dashes and otherwise a fresh UUID, and `user_id` in
`platform/security.py::resolve_principal` once the principal resolves.

The runtime binds the task's keys around the whole durable call, so its
`durable tool failed` line and its settle lines carry them. The task row holds
no site, so the runtime's own lines outside the body name none: the
`durable tool failed` line, the settle lines and the lines of a completion
turn written before `run_turn` resolves the thread's site. The lines
procrastinate writes before and after it calls a job are outside every block.

# The same numbers without Langfuse

`uv run python -m pathfinder.devtools.usage report [--since DATE] [--site X]` reads
the `messages` rows and prints cost and tokens per conversation (with turns, site,
assistant and researcher), per researcher and per day, and the averages. See
`apps/api/src/pathfinder/devtools/README.md`.
