---
type: Decision
title: Nothing unknown becomes a default
description: What Strategist cannot compute, parse, verify or read is refused or shown as missing with a reason; it never becomes a default value, a silent choice or a reply that claims more than the turn did. Defaults per caller, prose matching, a model call to choose among same-named entries, a transform read by record type, a classifier of every body ValidationError and a generic unknown at every call site were rejected.
tags: [agents, honesty, wdk, verification]
generated: { by: claude-code/opus-5.5, at: 2026-11-24T00:00:00Z }
status: stable
---

# What was decided

Three rules, each owned by one type or function and held by one gate: a reply is rendered
from facts the turn holds; every choice among candidates is stated or refused; a missing
input is a typed unknown.

**G1. A missing input is a typed unknown.** `domain/unread.py::Unread(reason)` is one frozen
model, used only by a service reader whose consumer must continue without the value: the
data marks, the tunable read, the membership re-read, VERIFY's decode of what the site holds.
Where the domain already has a typed unknown it is used instead:
`SiteCheck(status="unchecked", why_unchecked=...)`, `UnreadOrganisms`,
`not_verified(..., "no_value_to_compare")`. A consumer matches on `T | Unread` in the one
type or function that owns the rule, never at each call site. A tool read that fails on the
site has no `except`: the call fails through `SiteReadFailures`.

**G2. An absence is a claim only over a read.** "The site has no search for X" stands only
when a recorded catalog read of the pass (`CatalogRead`) covers the plan's input classes;
otherwise FRAME's report is refused once and then becomes "not read", with the read that
would answer it. One reader, `services/strategies/record_classes.py::transforms_accepting`,
lists the transforms whose primary input accepts a class the plan holds, across every record
type of the site; `list_transforms` and `role_problems` both read it.

**G3. A value is stated only through `value_source()`.** A `BoundValue` source `stated` is a
`StatedSource`, minted only by `value_source()`; the restatement paths call it with the
parameter's vocabulary. A value is stated only when a request message names it and joins no
other entry of the same vocabulary to it that the binding leaves out; otherwise it is
`chosen`.

**G4. Entries that share a display name are one name.** veupathdb-py groups them
(`same_named_groups`) in one function that `match_exact_option`, `exact_entry` and
`VocabLookup` read. A binding that takes a strict subset of a group is refused unless the
request names the bound entry by its accession. The organism fold drops a leaf by count
identity only.

**G5. A WDK reply that does not parse is a site failure.** `SiteReadFailures` fails the call
with the tool name and the reply model that did not parse. A `ValidationError` from a model
built from the call's arguments keeps its corrective retry.

**G6** is the runtime check of a changed strategy:
[the runtime checks a changed strategy, then the Lead answers](the-runtime-checks-a-changed-strategy-then-the-lead-answers.md).

**On `needs_user` nothing is said to be applied.** `EditDelta` and the `FrameResult` the Lead
reads say "Nothing was applied", and FRAME's draft rides as a `PendingPlan` that renders as
not applied. An applied change is what `TurnFacts` renders, never a third summary.

# The gates and their reach

- `apps/api/scripts/check_fail_open.py` (pre-commit `fail-open-api`, CI) fails an `except`
  handler in `ai/`, `services/` or `domain/` that returns, assigns or passes an empty value,
  ends in `pass` or `continue`, or only logs, nested, keyword and helper-log shapes included,
  unless `scripts/fail-open-allowed.txt` lists it by `path:function:ordinal` with its reason.
  It reads only those three packages and only `except` handlers: a fallback written as a
  conditional, or one in `transport/`, `jobs/` or `persistence/`, is outside it.
- A test holds every construction of a stated value source to `value_source.py` and
  `stated_source.py`.
- A type test holds every result the Lead reads from a dispatch to no stored `summary: str`.

# What was rejected

**A default per caller.** Each caller chose its own value for what it could not read; the
parameter sweep's metrics substituted 0.0 for an unmeasured value, so rows read as measured.

**Prose matching** of the reply against what was written. The recorded decision
[a reply states what the turn wrote](a-reply-states-what-the-turn-wrote.md) stands.

**A model call to choose among same-named entries.** They are one name to the researcher; the
researcher chooses, or the request names an accession.

**A transform read by the plan's record type.** It hides a transform whose input class is
listed under another record type, such as `GenesByOrthologs` for a transcript plan.

**A classifier of every body `ValidationError`.** It ends the corrective retry of models the
model builds from its own arguments.

**A generic unknown at every call site.** It is the caller-side copy the rule exists to
remove; the unknown lives on the type that owns the rule.

# Measurement

QA, `openai:gpt-5.6-luna` on every role, the same goals and harness on both sides. Before is
the re-measure of 0.9.1a17 (cause G not merged); after is that release with G and the step
check of one definition merged. The G counts are recorded instances: before over every run of
the re-measure (277 run directories), after over this batch's runs (the 12 eval cases, the
sibling-strain and dry-c repeats and the goals e1, a2, d3, b1, e2).

| item | before | after |
|---|---|---|
| G-a: a needs_user draft claimed as applied | 1 | 0 |
| G-c: a drop card over a requirement the build grounds | 0 | 0 |
| G-d: a strict subset of a same-named group | 0 | 0 |
| G-e: `stated` while the request names another entry | 1 (e10) | 0 (e10 not run, site down) |
| G-f: an organism-fold drop below the universe | 0 | 0 |
| G-g: `bound_values` fails over the leaves the push sent | 0 | 0 |
| G-h: a verdict passes with every record read failed | 0 | 0 |
| G-i: `list_transforms` hid a transform of a plan class | 10 | 0 |
| sibling-strain eval, plan path (no EDA route) | 1 of 2 pass | 2 of 2 pass |
| changed turns of the goals: mean Lead calls | 5.33 (6 goals) | 4.80 (5 goals) |
| changed turns of the eval cases ending with a verdict | 12 of 19 | 17 of 22 |
| nothing-verified refusals | 9 | 0 |

The sibling-strain eval fails whenever the model takes the EDA route for the expression step
(a durable compute, which an in-process eval declines), on both sides; that route is not a G
item.
