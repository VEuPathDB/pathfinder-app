---
type: Backlog
---

# A criterion carries the reason its search was chosen

Release a15. The Lead's replies say what a step runs (its search's display name)
and what the researcher asked for (the subtitle), but never why that search was
chosen over the others FRAME saw. The researcher asked for this after the demo:
the model should say why it chose a search, and prompting a terse model for
verbosity is not the fix.

## What

FRAME records a one-line `rationale` on the criterion at binding time, from what
it actually compared: the searches the catalog answered with their similarity,
the one it bound, and the reason (the parameter that carries the requested value,
the record type, the organism scope, or "the only search that names X"). The
rationale travels with the spec, is rendered under the step's subtitle on the
canvas and in the step results section, and the reply's contract requires it for
every added search beside the name (`unnamed_search` grows a second clause).

## Constraints

Grounded, not generated: a rationale that names a search the catalog never
answered fails the contract like an unnamed search does. A re-import from WDK
loses it like the subtitle (the same `StepWords` metadata carries it). Regression
tests: the binding records the alternatives it saw; a rationale naming an unseen
search is refused; the canvas and the reply render it.
