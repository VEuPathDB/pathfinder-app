---
type: Backlog
---

# The EDA filter sheet is lost to the history elision

**What I did.** Called `set_eda_filters(dataset_id)` for the phenotype study with no filters, so
it answers with the sheet; made four other tool calls; ran the runtime's own `elide_consumed`
over that history; then called `set_eda_filters(dataset_id)` again for the same study.

**What I got.** The first sheet carries 13 variables, 55 vocabulary values and 6,676 characters
on the wire. After the four later calls, the same return is 294 characters and ends `... <elided
to control context size; already acted on, do not fetch again>`. The second sheet carries the
same 13 variables and **0** vocabulary values, each with the note "vocabulary shown in the first
sheet for this study; ask preview_eda_subset for this variable's distribution to see the values
the current subset holds".

**Why that's wrong.** The values the note says the model already holds are gone: the elision
took them, and the second sheet refuses to send them again. The model then writes a filter value
it cannot see, and a value that is not in the study gets a rejected subset or a silently empty
one, so the researcher reads a filtered analysis whose filter never matched. The route the note
offers, `preview_eda_subset`, is one call per variable, which is the cost the sheet exists to
avoid.

**Why it happens.** `sheet_for` in `ai/tools/standalone/_eda_sheet.py` strips the vocabulary
from every later sheet for a dataset (`was_eda_sheet_shown` / `mark_eda_sheet_shown`,
`_RE_SHEET_NOTE`), on the assumption that a return the model saw once is a return it still
holds. `elide_consumed` (`assistant_core.conversation.history`) keeps only the three most recent
tool returns whole and cuts every older one to its first 220 characters, so the assumption is
false for any sheet the model copies from later. This is the same defect FRAME's parameter sheet
had.

**Fix.** Pin it the way FRAME's sheet is pinned: hold the open EDA filter sheet in state, render
it in the instructions of the agent that reads it until the subset is applied, answer the
opening call short, and delete `_RE_SHEET_NOTE` with the second-sheet stripping. Bound the pin
the way `PINNED_SHEETS_MAX_CHARS` bounds FRAME's. Red first: a test that after the sheet call
and four unrelated calls under `elide_consumed`, the rendered instruction still carries the 55
values.

**What you'd get.** A filter written many calls after the sheet was opened names a value the
study holds, and no variable costs a `preview_eda_subset` call to read what the sheet already
sent.
