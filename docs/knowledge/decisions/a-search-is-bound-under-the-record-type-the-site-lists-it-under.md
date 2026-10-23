---
type: Decision
title: A search is bound under the record type the site lists it under
description: Every read of a search's definition (set_criterion, the qualifier comparison, the Lead's sheets and the analysis kinds) uses the record type the site's catalog lists the search under; a search the catalog lists under none has no sheet and no kind, and the read names it; set_criterion refuses a name the catalog lists under none; a 404 on the search's own lookup is the site's refusal, recorded for the pass and refused by name after that without a site read; past the repetition threshold the pass stops with its own reason, "stopped on a search the site does not serve"; an input-dataset parameter takes typed ids saved as the site's ID list, or a dataset id in the typed form. The root's record type (also as the fallback for an unlisted search), a fix-your-arguments directive, a cap on set_criterion and a named budget in the runtime's guard were rejected.
tags: [agents, frame, parameters, wdk]
generated: { by: claude-code/opus-5.5, at: 2026-10-22T00:00:00Z }
status: stable
---

# What was decided

A strategy can hold leaves of more than one record type: a transform from
proteins to groups has a protein leaf under a group root. WDK serves each search
under one record type (`WdkModel.getQuestionByName()`). So every read of a
search's definition looks the record type up in the site's catalog first
(`record_classes.search_record_types`):

- `set_criterion` and the qualifier comparison of its neighbours;
- the Lead's sheets (`sheet_params`, read by the replay of an outside change and
  by a consult answer);
- the analysis kind of a step (`analysis_kinds`).

A search the catalog lists under no record type has no sheet and no analysis
kind. The read logs "the site lists no record type for the search" with its
name, and the caller keeps the values it holds for that search, as for a
search the site cannot read.

`set_criterion` adds these rules:

- **A name the catalog lists under no record type.** The call is refused by
  name, and the site is not asked. The name is recorded in `unserved_searches`
  and counts toward the limit below. A report of it as
  `site_refused_the_search` is sent back naming it as `site_has_no_search`.
- **A 404 on the search's own definition read.** The 404 can come from
  `read_search_definition`, from the catalog's read, which wraps it, or from the
  first parameter read. It is the site's refusal of the search. The pass records
  it in `refused_searches`, so FRAME's report `site_refused_the_search` holds.
  It also records it in `unserved_searches`, so a later call that names the
  search is refused by name and the site is not asked again.
- **A 404 elsewhere in the bind.** A 404 from a dataset save or a vocabulary
  refresh is reported as what it is, and the search stays bindable.
- **The limit.** Each refusal of an unserved search counts per pass. Past the
  runtime's repetition threshold, `SearchNotServedError` ends the pass. It is
  mapped to `PhaseStopReason.SEARCH_NOT_SERVED` ("stopped on a search the site
  does not serve"). Its words name the search, the site and the record type,
  and the Lead and a continuation pass read them.
- **An `input-dataset` parameter.** It takes the ids the request states, split
  on the separators the site's own ID list box splits on (`[;,\s]+`, wdk-client
  `DatasetParamUtils.idListToArray`). It also takes the typed form the tool
  server shows, `{"type": "input-dataset", "datasetId": ...}`, which holds the
  ids or a real dataset id. A plain value is always ids, even a numeric one; a
  dataset id comes only through the typed form. The ids are saved as an `idList`
  dataset once per criterion and ids in a pass. A gene set and an edit save
  theirs the same way (`services/strategies/dataset_sources.py`). The bound
  value is the dataset, its label is the ids, and it is stated when a request
  message names them.

# Rejected

- **The strategy root's record type.** It is right only for a leaf of the root's
  record type, and the site answers 404 for every other leaf.
- **The strategy's record type as the fallback for an unlisted search.** A
  search's sheet lives under its own record type
  (`/record-types/{rt}/searches/{name}`), so a guessed type reads another
  sheet or answers 404. An unlisted search is stated as unknown instead.
- **A 404 returned as a directive to correct the arguments.** No argument of
  `set_criterion` names a record type, so no correction exists. A returned
  directive also spends no retry, so nothing ends the loop.
- **A call cap on `set_criterion`.** A pass binds several criteria and calls it
  twice for each, so a cap on the tool stops a pass that is making progress.
- **A named budget in the runtime's repetition guard.** The guard's budgets are
  keyed by tool name, and its stop reports a call budget the tool does not have.
  The cause is the site's, so the stop names it.
