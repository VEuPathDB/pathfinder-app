---
okf_version: "0.2"
---

# PathFinder Knowledge Bundle

Curated, durable knowledge about PathFinder in [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) v0.2. Plain markdown with YAML frontmatter, no tooling required: if you can `cat` a file you can read it.

This is not a replacement for `CLAUDE.md` (rules an agent must follow every session) or for code comments (why this line is this way). It holds what neither can: decisions with their reasoning, work we know is outstanding, and how VEuPathDB's WDK behaves, pinned to the upstream that can prove it wrong.

## Backlog

- [Backlog](backlog/) - everything known to be outstanding, ranked

## Decisions

- [Decisions](decisions/) - choices made deliberately, with the evidence and the alternative that was rejected

## Conventions

- [Conventions](conventions/) - how we work and how this bundle stays true

## WDK

- WDK (`veupathdb-py: docs/knowledge/wdk/`) - how WDK works, how PathFinder maps onto it, and the rules that must hold

## EDA

- [EDA](eda/) - how PathFinder adopts VEuPathDB's Exploratory Data Analysis platform: the two seams and the layer placement
- [Integration concept](eda/pathfinder-integration-concept.md) - the two seams, an EDA tab of its own, and how models get EDA knowledge
- [Architecture fit](eda/pathfinder-architecture-fit.md) - where every EDA concern lands in the layer model, the durable-tool mapping piece by piece, the MCP/SDK placement, and the SSOT for the analysis spec

What EDA itself is, and every wire fact these two stand on, is the client library's bundle at `veupathdb-py: docs/knowledge/eda/`.

## History

- [log.md](log.md) - dated record of significant changes to this bundle
