---
type: Decision
title: A turn's records sit in an appendix below the reply
description: The parts a turn writes as its record (the facts, the evidence card, the control tests, the strategy's state, the sources, the recalled memories, the EDA setup) draw in one closed appendix below the reply, lettered and in two columns from three sections; results, cards that ask for a click, and turn notices stay in the reply.
tags: [thread, figures, layout, facts, evidence]
generated: { by: claude-code/opus-5.5, at: 2026-10-16T00:00:00Z }
status: stable
---

# What was decided

`TurnAppendix` (`features/conversation/thread/TurnAppendix.tsx`) draws, below an assistant
message's reply, the parts `APPENDIX_KINDS` names (`content/appendixParts.ts`), each through
its own card in a lettered section (`A. Strategy`, `B. Evidence`, ...) in that fixed order.
In the reply flow those kinds draw nothing, so the trace does not split a run at them.

| Stays in the reply | Goes to the appendix |
|---|---|
| The reply text | `data-facts` (`Strategy`), less its notices |
| Cards that ask for a click (`CARD_TOOLS`), gene sets | `data-evidence-card`, `data-control-test-results` |
| EDA plots, PCA, statistics, comparisons, separations | `data-graph-snapshot`, `data-strategy-link`, `data-strategy-meta` (the last of each) |
| Turn notices: stopped, failed, withdrawn, and the facts' refusal and stopped check | `data-research.sources`, `data-memory-retrieved` |
| | `data-eda.analysis-state` (the last), `data-eda.subset-preview` |

The appendix starts closed. Its closed line names the section count, the last facts' result
and its caveats and gaps. A link to an exhibit it holds (`#table-<n>`, `#figure-<n>`) opens
it. From three sections it reads in two columns on a wide screen, with the facts, the evidence
card and the control tests across both; on a phone it is one column. One unlayered rule in
`styles/globals.css` gives every section one body size and one heading size, over the size
classes each card carries. The facts list the records a turn read, the genes the message
names, each listing and each record's orthologs as tables of ten rows a page
(`ExhibitTable`'s `pageSize`), so a long list never runs the appendix long.

# Rejected

- **Every card in the reply flow, as before.** The reply sat under the cards it summarizes;
  a build turn drew its reply after about 4,000 px of records.
- **Hiding the facts entirely.** The reply restates no fact, so the result count stays on the
  closed line and the refusal stays in the reply.
- **A per-card collapse.** It keeps each card's own type and spacing, and the records still
  stand between the trace and the reply.
