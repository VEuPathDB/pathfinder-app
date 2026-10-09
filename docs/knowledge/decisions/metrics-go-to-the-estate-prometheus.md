---
type: Decision
title: Metrics go to the estate's Prometheus, on a port apart from the app
description: The api and the worker each serve their Prometheus series with prometheus_client's own server on METRICS_PORT (9100) at METRICS_ADDR, never as a route of the FastAPI app, and the estate's promdock scrapes them on the monitoring network. Labels hold a route template, an assistant, an outcome, a model and a payer, never a user, a conversation or a raw path. Langfuse stays out of the estate stack, so the estate keeps traces as logs. A /metrics route on the app, the OpenTelemetry Prometheus bridge and a FastAPI instrumentator were rejected.
tags: [observability, prometheus, metrics, deployment, worker]
generated: { by: claude-code/opus-5, at: 2026-10-08T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-10-08T00:00:00Z }
status: stable
---

# What was decided

The estate runs one Prometheus, `promdock`. It scrapes every container on the
`monitoring` network that carries `prometheus.scrape_enabled=true`, the way it
scrapes `eda-service` and `vdi-service`. The api and the worker units join that
network and carry that label.

**Each process serves its series on a port of its own.** `platform/metrics.py::serve_metrics`
starts `prometheus_client.start_http_server` on `METRICS_PORT` (default 9100; 0
serves none) at `METRICS_ADDR` (default `0.0.0.0`, because the scraper reaches the
container over the monitoring network). The api starts it in its lifespan and
closes it at shutdown; the worker starts it in `jobs/worker.py::amain`. Both answer
`GET /metrics` on 9100. Neither compose nor the units publish the port.

**The app has no metrics route.** The website's rewrites forward `/api/*` and
`/health/*` to the api, and the api unit is not routed by traefik. A route on the
app would still be published by the first rewrite or proxy change that forwards
more of it, so the series live on a server the app does not serve.

# What is collected

| series | process | labels |
|---|---|---|
| `pathfinder_http_requests_total` | api | method, route template (`unmatched` when none), status class |
| `pathfinder_http_request_duration_seconds` | api | method, route template; time to the response headers, so a stream counts its first frame |
| `pathfinder_chat_turns_started_total` | api | assistant; one per queued turn |
| `pathfinder_chat_turns_finished_total` | worker | assistant, outcome (`completed`, `failed`, `stopped`), the model that read the prompt |
| `pathfinder_chat_turn_duration_seconds` | worker | assistant, outcome |
| `pathfinder_model_tokens_total`, `pathfinder_model_cost_usd_total` | worker | model, payer (`deployment` or `user`) |
| `pathfinder_tool_source_errors_total` | worker | admitted source id, stage (`open` or `call`) |

The worker reads a turn's spend from the usage chunks the turn already writes
(`jobs/turn_metrics.py`): the Lead's usage and each sub-agent dispatch under their
models, and what the turn total holds beyond them under the turn's model. The payer
is `turn_paid_by` for that model inside the turn's key scope. The chunks carry
total tokens and cost, not the input and output split, so the token series has no
direction label. A tool's own `ModelRetry` is not a source error. The default
process and garbage-collector collectors stay on.

Nothing names a user, a conversation, a site's free text or a raw path. A route
label is the template FastAPI matched (`/api/v1/conversations/{strategyId:uuid}`).

# What stays out

Langfuse is not part of the estate stack. Its traces, prices and scores belong to
the development deployment that runs it
([Traces go to one self-hosted Langfuse over plain OTLP](traces-go-to-langfuse-over-plain-otlp.md)).
In the estate, with no OTLP endpoint set, a turn is read from the structured JSON logs
of the api and the worker, and the runtime's own OpenTelemetry instruments export
nothing.

# Rejected

- **A `/metrics` route on the app, left out of the spec.** It is internal only while
  every proxy in front of the api forwards nothing but `/api` and `/health`.
- **The OpenTelemetry Prometheus exporter over the runtime's instruments.** It is a
  pre-release package, and those instruments carry no assistant, model or payer.
- **A FastAPI instrumentator.** It adds a framework for one middleware, and labels a
  path by its handler options rather than by the template the router matched.
