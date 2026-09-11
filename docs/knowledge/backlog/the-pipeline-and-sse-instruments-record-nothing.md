---
type: Backlog
title: The pipeline and SSE instruments record nothing, because nothing imports them
description: platform/metrics.py creates 19 OTEL instruments and no module in this repository imports it, so every pathfinder.pipeline and pathfinder.sse series is empty while the exporter runs; the code that would emit them now lives in the runtime, and vulture at min_confidence 80 does not report an unused module-level binding.
tags: [observability, metrics, assistant-core, dead-code]
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
status: stable
---

# What I did

Counted the instruments in `apps/api/src/pathfinder/platform/metrics.py` and
searched the repository for anything that imports the module or names one of
its instruments.

# What I got

The file is 137 lines and creates 19 instruments: 13 on the
`pathfinder.pipeline` meter (runs, turn duration, time to first delta, time to
first message, time to first tool call, approval wait, resume after approval,
execution duration, phase events, phase duration, token usage, errors,
recoveries) and 6 on the `pathfinder.sse` meter (subscriptions, active
subscriptions, subscription duration, disconnects, events sent, keepalives
sent).

Searching `apps/api/src`, `apps/web/src` and `packages/` for
`platform.metrics` returns no production hit, only prose in `docs/`. Searching
for the instrument names returns the definitions and nothing else. Meanwhile
`platform/observability.py:148-149` builds a `MeterProvider` and installs it,
so the process exports metrics and these 19 series carry no points.

`apps/api/pyproject.toml:193-199` sets `min_confidence = 80` for vulture, which
does not report an unused module-level binding, so the dead-code gate is green.

# Why that's wrong

An operator watching this deployment has a dashboard of empty charts: there is
no series for turn duration, none for tokens, none for SSE disconnects, and
nothing says the instruments were never wired. The first person to debug a slow
turn reads "no data" and cannot tell an idle system from an uninstrumented one.

# Why it happens

The turn and the SSE pipeline moved into `assistant_core.graph` and
`assistant_core.conversation.event_stream`, and the instruments stayed behind in
`platform/metrics.py` with no caller.

# Fix

Library first, in `ai-assistant-platform`: the runtime gets its own instrument
module and records from the code that owns each event, the turn in
`assistant_core/graph` and the subscription in
`assistant_core/conversation/event_stream.py`. Then here: delete
`platform/metrics.py`, keep `platform/observability.py`, which configures the
provider the runtime's instruments report through, and take the instruments at
the library's next tag. Drop the `metrics` entry from the `platform/` line of
the backend directory in `CLAUDE.md` in the same change.

# What you'd get

Turn duration, token usage and SSE disconnects arrive from the process that
observes them, for every assistant, and this repository holds no instrument
that records nothing.
