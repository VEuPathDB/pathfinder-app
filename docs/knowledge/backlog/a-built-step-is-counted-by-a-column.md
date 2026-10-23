---
type: Backlog
title: A member count reaches framing on the first message
description: A question that counts the members of a result by a column (the proteins of single-protein ortholog groups, by organism) is classified a follow-up question on a conversation with no strategy, the column tally guesses a search the catalog lacks, and the turn asks which site; the first message must reach framing, build the transform and answer with the site's tally.
tags: [lead, tools, tally, orthomcl]
generated: { by: claude-code/opus-5, at: 2026-10-23T00:00:00Z }
status: proposed
---

# A member count reaches framing on the first message

## What happens

"Which organisms in OrthoMCL have the most singletons (ortholog groups with one
protein)?" On a conversation with no strategy the first message is classified
`follow_up_question`, which withholds `frame_problem` and `build_strategy`. The Lead
has no catalog search of its own, so `count_by_column` guesses a search name the
catalog does not list; the refusal said only that the site has no search of that
name, and the turn asked which site to use. The same request sent again as a build
reaches FRAME, which binds `GroupsBySequenceCount` and the `FromGroups` transform, and
`count_step_by_column` answers with the site's per-organism tally.

## Change

1. The column tally's refusal of a search the catalog lacks, on a conversation that
   holds no step and has not framed, names the reroute: with the message classified
   `new_strategy`, dispatch `frame_problem`, and count the built step with
   `count_step_by_column` (`ai/tools/standalone/search_reads.py`). Done.
2. The classifier still names every count per value of a column a follow-up
   question. The Lead's own rules name a count of a result's members as the
   transform then `count_step_by_column`; whether the first message now reaches
   framing is unmeasured.

## Done when

A replay of the singleton question's first message reaches `frame_problem`, builds
the transform, and answers with the site's per-organism tally in one turn.
