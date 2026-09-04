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

- [WDK](wdk/) - how WDK works, how PathFinder maps onto it, and the rules that must hold

## EDA

- [EDA](eda/) - VEuPathDB's Exploratory Data Analysis platform, how it reaches WDK steps, and the PathFinder integration concept

## History

- [log.md](log.md) - dated record of significant changes to this bundle
