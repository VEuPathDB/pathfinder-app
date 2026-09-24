---
type: Backlog
---

# A researcher brings their own provider key

Release a15. Every turn is metered against the deployment's quota and runs the
deployment's default model. A researcher who wants a stronger or chattier model,
or who runs many turns, has no way to pay for it themselves.

## What

A provider API key per user and provider, entered in Settings, validated once
against the provider (a one-token call), stored encrypted at rest under a
server-side secret, never logged, revocable. A turn under a user key runs on that
key: the quota pill shows the bare figure (`x.yz`, not `x.yz/20`), the usage
telemetry still records every token, and the model catalog offers that
provider's models to that user.

## Constraints

The key never reaches the browser after entry, never appears in a log, a trace
or Langfuse, and is scoped to the user who entered it. The worker reads it at
turn start through the job context, the way the WDK token travels today. A key
the provider refuses is reported once and the turn falls back to nothing (the
turn is refused, not silently metered). Regression tests: encrypt and decrypt
round-trip, a revoked key is not read, the pill's two shapes, telemetry rows
under a user key, a refused key's error.
