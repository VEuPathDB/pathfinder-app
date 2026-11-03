---
type: Decision
title: A record type's role is read with its class
description: The message reading writes a record type's role, answer or through, beside its record class on the typed value, and the record-type check reads it there. FRAME stating a role for each record-type requirement on every pass, kept by requirement id on the thread, was rejected.
tags: [requirements, verification, frame, lead]
generated: { by: claude-code/opus-5.5, at: 2026-11-03T00:00:00Z }
status: stable
---

# What was decided

`RecordTypeValue` (`domain/strategy/constraints.py`) holds `record_class` and
`role`. `answer` says the result is those records; `through` says the result is
records of another class that those records lead to, as in the ortholog groups
of given proteins. The message reading writes both from the researcher's words
(`ai/prompts/stated_request.md`), with `answer` when the words state no role.
The record-type check (`domain/requirement_checks.py::record_type_check`)
compares an `answer` with the class of the result step and a `through` with the
class of every step of the tree; a record type with no value is unchecked.

# Why

The role is a fact of the request, as the class is: "the proteins whose ortholog
groups have no mammal protein" wants proteins as the result and passes through
groups whatever tree is built. Over five runs on the labelled OrthoMCL turns the
reading wrote the role the hand label gives for every record type it extracted,
`through` included. One writer keeps one value: two writers of the same
fact on one requirement need a rule for which wins, and the check would read a
role the requirement does not show.

# What was rejected

**FRAME states the role on every pass.** `FrameResult.record_types` named a role
for each numbered record-type requirement, an output validator sent a pass back
that left one out, and the thread kept the roles by requirement id
(`record_roles`). It cost an output field, a refusal and a stored map for a fact
the reading already holds, and it let a pass restate the request's meaning from
the tree it built. A stored `record_roles` map is ignored on load; the stored
record type is untyped until the researcher states it again.

# Anchors

`domain/strategy/constraints.py`, `domain/message_reading.py`,
`domain/requirement_checks.py`, `ai/lead/verify_checks.py`,
`ai/prompts/stated_request.md`.
