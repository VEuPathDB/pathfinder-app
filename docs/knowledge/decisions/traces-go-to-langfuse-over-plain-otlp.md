---
type: Decision
title: Traces go to one self-hosted Langfuse over plain OTLP
description: The api and the worker export OpenTelemetry traces over OTLP/HTTP to a Langfuse that runs on the deployment's own host; product events and rating scores use the Langfuse SDK on a tracer provider of its own. SigNoz beside Langfuse, the Langfuse SDK's span processor, and Langfuse Cloud were rejected.
tags: [observability, langfuse, tracing, deployment]
generated: { by: claude-code/opus-5, at: 2026-09-28T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-28T00:00:00Z }
status: stable
---

# What was decided

One backend holds the LLM traces, their cost, the product events and the rating
scores: Langfuse v3, self-hosted as six units beside the application
(`quadlets/pathfinder-langfuse*.container`, `docker-compose.observability.dev.yml`).

The runtime installs a plain OpenTelemetry `TracerProvider` whose exporter is the
SDK's own `OTLPSpanExporter`, configured by the standard `OTEL_EXPORTER_OTLP_*`
variables. The api and the worker both install it; the worker is where every model
call runs. The host adds only the basic-auth header Langfuse's ingress reads. The
Langfuse SDK is used for scores and events alone, and is given a private
`TracerProvider` so it never attaches to or replaces the process's provider.

What a trace holds is `conventions/observability.md`.

**The estate stack carries no Langfuse**
([the images decision](the-images-come-from-the-registry-and-cedar-pulls.md)).
A process with `OTEL_EXPORTER_OTLP_ENDPOINT` unset exports no traces, so traces
exist only where a deployment runs Langfuse beside the application: local
development (`docker-compose.observability.dev.yml`) and the interim rootless
deployment (`quadlets/pathfinder-langfuse*.container`), which the cutover to the
estate stack deletes.

# What was rejected

**SigNoz beside Langfuse.** Two backends meant two exporters, two UIs, seven more
services and a browser tracer, and neither answered the operator's questions alone:
SigNoz had no prompts or model cost, Langfuse no infrastructure spans. The
questions a user acceptance test asks are about turns, cost and use, which one
LLM-aware store answers. The browser OpenTelemetry and its proxy went with it: its
error spans had no reader, and the product events it could not express now go to
the server.

**The Langfuse SDK's span processor.** It attaches to whatever global provider it
finds and filters spans by instrumentation scope, so a span the application opens
itself was dropped unless a custom filter kept it. It also ties the runtime, which
serves hosts that are not PathFinder, to one vendor's SDK. Plain OTLP keeps the
runtime vendor-neutral: pointing the endpoint at any OTLP backend needs no code.

**Langfuse Cloud.** Traces carry researchers' prompts, gene lists and unpublished
hypotheses when content export is on. Self-hosted, that data stays on the host that
already holds the conversations, behind the same SSH tunnel, and content export can
be on by default.
