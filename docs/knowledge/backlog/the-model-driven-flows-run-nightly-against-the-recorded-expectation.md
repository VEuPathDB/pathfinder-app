---
type: Backlog
---

# The model-driven flows run nightly against the recorded expectation

Most pre-UAT findings were model behaviour: a word read as a qualifier, the
synteny default, a control id dropped from a tool call. The mock stack cannot
catch these, because the mock plays a script. The UAT flows whose expectation is
a model decision (which search binds, which tree is built, which refusal is
written, which count the card reports) are today checked by hand through
`pathfinder.devtools.chat`, one turn at a time.

## What

- Each such flow becomes a scripted devtools check: the prompts in order, the
  site, the effort, and the recorded expectation from `docs/knowledge/uat/` (the
  tree shape, the counts with their site build, the refusal sentence).
- The checks run nightly on the real model (`openai:gpt-5.6-luna`) in CI, with
  the deployment's key, and a drifted count is a re-measure while a changed tree,
  a missing refusal or a wrong unit is a failure.
- Each case joins `evals/corpus/` so the structural scorer reports the same
  drift, and the eval runner passes the effort through.

## Done when

Every model-driven UAT flow has a nightly check with a recorded expectation, the
nightly run is a release gate beside the hermetic integration tier, and the
`docs/knowledge/uat/` coverage matrix names the check for each flow.
