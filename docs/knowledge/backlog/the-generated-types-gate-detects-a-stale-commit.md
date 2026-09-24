---
type: Backlog
---

# The generated-types gate detects a stale commit

`packages/shared-ts` `check:generated` runs Kubb and then `tsc --noEmit`: it rewrites
every file under `src/generated` in place and type-checks the result, so a committed
output that no longer matches the spec passes the gate and is silently replaced in the
working tree. The OpenAPI freshness check (`pathfinder.devtools.openapi check`) covers
the spec itself, not the TypeScript generated from it.

In CI the checkout is clean, so the gate can compare: regenerate, then fail when the
regenerated tree differs from the committed one (the CI job runs git; the pre-commit
hook can compare against a content hash written beside the output instead). Add the
comparison to both, and a test of the checker that fails on one stale file.
