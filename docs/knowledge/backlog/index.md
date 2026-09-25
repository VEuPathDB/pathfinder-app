# Backlog

Everything known to be outstanding, ranked by what actually moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

1. [Every UAT flow runs end to end on the mock stack](every-uat-flow-runs-end-to-end-on-the-mock-stack.md) - a17: one spec per user-driven UAT flow, arcs that take their values from the site, the suite green on plasmodb and vectorbase.
2. [The model-driven flows run nightly against the recorded expectation](the-model-driven-flows-run-nightly-against-the-recorded-expectation.md) - a17: scripted devtools checks on the real model with the recorded counts and trees, joined to the eval corpus, as a release gate.
3. [The mock plays a wrong model, and the suite runs in shards](the-mock-plays-a-wrong-model-and-the-suite-runs-in-shards.md) - a17: fault-injecting arcs prove every guard from the browser; the turn-driving specs run in parallel and the job is sharded (measured 23.7 min today, 18.5 of it the Playwright run).
4. [The Claude models are probed for images and documents](the-claude-models-are-probed-for-images-and-documents.md) - BLOCKED on keys: the deployment runs the OpenAI models for now; the probe runs when the Gemini and Claude accounts hold credit and the user says so.

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [One injection judge, and what a failed judgement means](../decisions/one-injection-judge-and-what-a-failed-judgement-means.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
