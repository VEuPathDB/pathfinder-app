---
type: Decision
title: The default effort is medium and VERIFY checks at high
description: The default tier runs every role on the provider's default model at medium and VERIFY at high; max as the default was measured on the benchmark cases and rejected for the wait it adds.
tags: [models, effort, tiers]
generated: { by: claude-code/opus-5, at: 2026-10-04T00:00:00Z }
status: stable
---

# What was decided

The default tier runs every role on the provider's default model,
`openai:gpt-5.6-luna`, at medium, and VERIFY at high. VERIFY checks at high in
every tier, on the model the tier gives BUILD (`platform/tiers.py`,
`_VERIFY_EFFORT`). BUILD runs no model; its role runs only `recover_failed_steps`,
on the tier's model, and Settings offers no pick for it. The effort a researcher
picks in Settings outranks the tier for its role, and no agent fixes an effort of
its own: the run's model settings are the only source.

# Why

The 19 benchmark cases ran once at each effort on one build, through the worker.
Max passed 15 of 19, the same count as medium, and took 10,426 seconds against
3,621, about three times the wait per conversation, for about 14% more cost. The
one case max fixed passes on a repeat at medium, and max failed one case medium
passed. VERIFY holds each claim of a turn to the reads that turn made, and the
medium cases were measured with VERIFY at high. The benchmark ran VERIFY on
`openai:gpt-6-luna`; the default runs it on `openai:gpt-5.6-luna`, the model the
Lead and FRAME plan on, for about 1.2 cents more per conversation at the
benchmark's usage.

# What was rejected

- **Max for every role.** No measured gain in what the turn gets right, and a
  researcher waits up to four times as long for a reply.
- **VERIFY at medium with the other roles.** It is a setup no benchmark arm ran.
- **VERIFY and BUILD on the provider's small model.** The small model checked the
  turn because a tier gave its worker roles the cheaper entry, not because it
  checked as well; the check is where a weaker model costs the answer.
