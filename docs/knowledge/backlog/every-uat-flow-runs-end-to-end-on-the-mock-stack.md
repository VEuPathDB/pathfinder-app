---
type: Backlog
---

# Every UAT flow runs end to end on the mock stack

`docs/knowledge/uat/` scripts 120 flows a researcher drives. The Playwright suite
(`apps/web/e2e/`) drives 167 specs against the mock model, but it does not cover
those flows one for one, and the mock arcs (`ai/models/mock/`) that the suite
depends on carry plasmodb values fixed in the code: a gene set id, a WDK step id,
PF3D7 gene ids and P. falciparum organisms. Nine of the 27 arcs are driven by no
spec at all: the ortholog round trip, the assent build, export, enrichment, the
parameter sweep, remember, the FRAME loop, off-topic and the kinase question.
Routing is substring matching in listing order, so "3d7" anywhere triggers a
build and a prose marker beats a build marker.

## What

- One spec per UAT flow that a user drives (the F, S, N, V, E, M, C, A, G, X and
  L families), asserting the flow's "Expect" column: the message, the card, the
  panel, the export, the setting.
- Every mock arc takes its values from the site the test opened (organism, a
  search the site lists, gene ids read from a step the arc built), never from a
  literal in the code; the arcs are routed by an explicit marker per flow, not by
  substring order.
- The suite runs on plasmodb and vectorbase in CI, so a site-specific value
  cannot pass unnoticed.

## Done when

Every user-driven flow in `docs/knowledge/uat/` names the spec that drives it in
the coverage matrix, every arc is driven by at least one spec, no arc holds a site
value, and the suite is green on both sites in CI.
