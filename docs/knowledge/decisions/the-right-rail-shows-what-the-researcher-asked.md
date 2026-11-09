---
type: Decision
title: The right rail shows what the researcher asked
description: The right rail holds Strategy, Review and a Study panel that appears with a study; Review states the question, whether each stated requirement is met, build problems, the spot check, the values chosen for the researcher and the caveats; six panels of pipeline state were rejected.
tags: [web, rail]
generated: { by: claude-code/opus-5.5, at: 2026-11-09T00:00:00Z }
status: stable
---

# What was decided

The right rail has three panels (`state/useRightRailStore.ts::RIGHT_RAIL_PANELS`): Strategy,
Review, and Study, whose button shows only while the thread has a study. Review
(`features/conversation/rail/review/`) is one scroll: what runs now, the question, a verdict,
each requirement the researcher stated with its status, the steps that failed or returned
nothing, the sampled genes by fit, the values the assistant or the site chose with a button that
asks to change one, the caveats, the assistant's notes and the memories the thread recalled.
`reviewModel.ts` derives all of it from the ledger, the latest evidence card, the running phase
and the strategy; the components only draw it.

The ledger is read section by section (`review/readLedger.ts`). A section the current schema
refuses is absent, and an unreadable entry of a listed array is dropped, so one retired value no
longer blanks the panel. A stored panel id from the six-panel rail opens its successor.

The rail sets no text under 12px, no uppercase labels, and monospace only for record IDs
(`rail/railType.test.ts`).

# Why

The six panels showed the pipeline's state: flag and counter rows, search and parameter
names, a context-window bar, every memory of every thread. A researcher reading the rail wants
to know what was asked, what was built, whether it holds up and what still runs. The data for
each answer was already in the thread.

# Rejected

- **Keep the six panels and restyle them.** The content, not the styling, was the problem: a
  restyled `open slots 0` row still answers no question a researcher asks.
- **Move the full evidence card into the rail.** The card stays in the thread, beside the reply
  it supports; Review summarizes it.
- **A context-window figure in the rail.** It is the assistant's budget, not the research.
