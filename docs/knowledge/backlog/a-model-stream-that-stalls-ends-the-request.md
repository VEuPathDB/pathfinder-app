---
type: Backlog
title: A model stream that stalls ends the request
description: A model response whose headers arrive and whose body stops leaves the turn waiting with no end; nothing in the stack bounds how long a stream may go without a new event.
tags: [models, streaming, reliability, worker]
generated: { by: claude-code/opus-5.5, at: 2026-10-06T00:00:00Z }
status: proposed
---

# A model stream that stalls ends the request

**What I did.** On the local stack, through the worker: "Which Plasmodium falciparum 3D7
genes are expressed in gametocytes? Use the site's default thresholds." on plasmodb, every
role on `openai:gpt-5.6-luna`.

**What I got.** VERIFY sent its eighteenth model request at 21:20:55 UTC; the worker logged
`POST https://api.openai.com/v1/responses "HTTP/1.1 200 OK"` at 21:21:00. No response was
captured, no chunk was written after 21:20:55, and the `chat_turn:run` job stayed `doing`
for more than twenty minutes. `python -m asyncio pstree 1` in the worker showed the turn
parked in `pydantic_ai/_agent_graph.py` `ModelRequestNode.stream._streaming_handler` on
`Event.wait`, with no WDK request in flight.

**Why that's wrong.** The researcher sees a turn that never ends and a stop that is the only
way out; the worker slot is held for as long as the stream stays open.

**Why it happens.** Not yet known. The response opened and its body stopped. Whether the
provider sent keep-alive bytes that reset the client's read timeout, or the read timeout is
longer than the stall, has not been measured.

**Fix.** Find what holds the stream open (the OpenAI client's timeout as pydantic-ai builds
it, and what arrives on the socket), then bound the time between two stream events and
retry or fail the request when it passes.

**What you'd get.** A stalled stream fails within the bound, and the turn retries the model
request or ends with its reply.
