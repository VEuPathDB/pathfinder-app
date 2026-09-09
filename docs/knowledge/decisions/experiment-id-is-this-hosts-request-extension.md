---
type: Decision
title: experimentId is this host's own request extension
description: The wire protocol ships an empty request-extension table, so the one field this application adds to the chat request body is documented and gated here instead of in PROTOCOL.md; naming it in the shipped protocol and dropping the field were both rejected.
tags: [protocol, chat, transport, assistant-platform]
generated: { by: claude-code/opus-5, at: 2026-09-09T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-09T00:00:00Z }
status: stable
---

# What was decided

`ChatRequestBody` accepts one field the wire protocol does not define:
`experimentId`, the experiment a thread records against. The protocol's
`request_extensions` table ships with a header row and nothing else, and its
prose says a host documents its own extensions. This page is that document.

The gate is `apps/api/src/pathfinder/tests/unit/ai/conversation/test_request_body.py`:
the core table names every field the body accepts except `experimentId`, and the
shipped extension table names none.

# Why

The protocol is one document shared by every assistant the runtime serves. A
field that only this application reads is not a rule a second host must follow,
and a table that lists it makes the wire look wider than it is.

# What was rejected

**Keep `experimentId` in `PROTOCOL.md`.** The name appears nowhere in the
runtime or in the client package; it was documentation of one product inside a
shared spec, and a second host reading the table would have implemented a field
nothing on the wire consumes.

**Drop the field and carry the experiment elsewhere.** The experiment is chosen
when the turn is sent and belongs to that request, not to the thread row: a
thread can be opened outside an experiment and later run inside one.
