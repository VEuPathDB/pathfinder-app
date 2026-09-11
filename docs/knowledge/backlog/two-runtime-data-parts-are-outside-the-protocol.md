---
type: Backlog
title: Two data parts the runtime emits are outside PROTOCOL.md, and PathFinder declares their schemas
description: data-memory-retrieved and data-scratchpad-updated are built and emitted by assistant_core but registered by ai/strategy_stream_parts.py, so the protocol table omits them, the library's own table gate cannot see the gap, and an assistant that is not PathFinder streams two kinds no spec defines.
tags: [protocol, assistant-core, stream-parts, site-help, generality]
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
status: stable
---

# What I did

Compared the data-part table in
`assistant-platform: packages/assistant-core/src/assistant_core/PROTOCOL.md`
against the kinds the runtime builds, and read who registers each payload
model.

# What I got

The table between the `data_parts` markers (lines 175-192) lists 12 kinds, and
`assistant_core/conversation/stream_parts/core_parts.py:29-40` registers the
same 12. The runtime builds two more:
`assistant-platform: packages/assistant-core/src/assistant_core/graph/stream_events.py:125`
returns `type="data-memory-retrieved"` and line 137 returns
`type="data-scratchpad-updated"`, the second from four call sites in the
runtime's own scratchpad toolset.

Both payload models are declared by this app:
`apps/api/src/pathfinder/ai/strategy_stream_parts.py:39-40` registers
`MemoryRetrievedPayload` and `ScratchpadUpdatedPayload`, imported from
`assistant_core.graph.stream_events`, inside a module whose own docstring
concedes that neither is a strategy concept. The web reads both:
`apps/web/src/features/conversation/rail/railActivity.ts:17,19`.

`assistants/site_help/spec.py:112-119` declares no `register_stream_parts`, and
`transport/http/openapi.py:42-43` builds the spec's data-part index from the
declarations the installed assistants make, so a deployment that installs only
a one-agent assistant publishes no schema for either kind while the runtime
still emits them.

# Why that's wrong

A second front end has nothing to build against: the two kinds are in no
protocol table and in no generated type, so the only way to learn their payload
is to read PathFinder's source. The library's table gate,
`test_the_data_part_table_lists_the_parts_the_runtime_registers`, compares the
table with the core registry, so as long as the two stay out of the core
registry the gate is green and the document stays incomplete.

# Why it happens

`register_core_stream_parts` omits the two payloads `graph/stream_events.py`
emits, so the app registers them instead.

# Fix

Library first, in `ai-assistant-platform`: register both payloads in
`assistant_core/conversation/stream_parts/core_parts.py`, which makes the
table test fail until `PROTOCOL.md` names both rows, and bump the protocol
version its changelog declares. Then here: drop lines 39-40 of
`ai/strategy_stream_parts.py` and the two imports above them, and take the
change at the library's next tag. The app keeps only the parts it owns.

# What you'd get

The two kinds appear in the protocol table and in the generated types of every
client, any assistant that uses memory or the scratchpad streams a documented
shape, and `ai/strategy_stream_parts.py` registers strategy concepts only.
