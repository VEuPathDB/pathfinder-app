---
type: Decision
title: A parameter the site sets is never asked for
description: A hidden or read-only parameter is site-set, a rule the parameter type holds; the model is never asked for one, a proposal of one is left out with a named correction, and what the model sees of a dependency skips site-set parents. Letting the model set an in-vocabulary hidden value was rejected.
tags: [parameters, frame, wdk]
generated: { by: claude-code/opus-5.5, at: 2026-11-21T00:00:00Z }
status: stable
---

# What was decided

Who sets a parameter is a fact of the parameter type. veupathdb-py
`WDKBaseParameter.site_set` is true for a parameter that is not visible or is
read-only, `bindable` is its negation, and `required` stands beside them. Every
reader asks the type: the sheet the model reads lists only bindable parameters,
no question card holds a site-set one, and the parameter rules class a site-set
parameter as `site_set`, whose source rule is `site`. A proposal that names a
site-set parameter is left out, whatever its value, with the correction
"<name> is set by the site, so the proposal was left out". FRAME records the
site-set names of each search it reads in a pass
(`AgentToolState.site_set_read_this_pass`), and a pass starts with the names of
every search whose values its draft carries
(`published_parameters_of_searches`, through the catalog's per-process
definition cache; a search the catalog cannot read is left out). Its option
check refuses nothing for those names, its question check holds none of them
(`card_answers.params_held`), and its bind return and empty-binding choices
show none. The turn reads the names of every search its specs carry when it
opens (`StrategyDomainState.site_set`, from the same cached read), each pass
adds the names it read, and no turn keeps them: the field is never written to
the checkpoint, so a site release that changes who sets a parameter is read on
the next turn. `diff_specs` counts a value the
spec before did not hold as moved only when the site does not set it, so the
ledger, the edit and its push never move a site-set value. `BoundValue.visible`
says only what the researcher is shown; no binding, asking or push decision
reads it. The catalog refuses a site-set value with `SiteSetParameterError`,
and a run fills each site-set value it lacks from its default
(`fill_site_set_defaults`). The web editor reads the same rule (`isShown`,
`isEditable`): a read-only field is shown and disabled, and `dependentParams`
stays WDK's full list.

A site-set value travels at the value a read under the bound parents gives. On
qa.plasmodb.org, `GenesByNgsSnps` under `organismSinglePick`
["Plasmodium vivax P01"] answers `eda_sample_table_suffix`
`sba1cd4a562_sample` (the published default is `s3be28bbe14_sample`), whether
the request leaves the suffix out or sends the stale one, and
`refreshed-dependent-params` answers the same value.

# Wire parents and stated parents

`ParamGraph` (veupathdb-py `domain/parameters/dependencies.py`) holds two
relations. Wire parents are every parent WDK declares, and only code that
mirrors WDK reads them: the dependent refresh, the deferral of a dependent
read, a measurement, and the checks that a parent moved. Stated parents are the
bindable ancestors reached through site-set parents, and everything the model
sees reads them. veupathdb-mcp `ParameterInfo` serves the stated relation and
keeps the wire relation unserved.

# Rejected

**Letting the model set a hidden value in its vocabulary.** A vocabulary check
does not make a hidden value safe. The website never draws a hidden parameter
and sends each one from its default or the saved step. Setting the hidden
RNA-Seq `channel` to its other entry made QA plasmodb answer 500, so a hidden
value in the vocabulary can still be a request the site cannot run.

**A list of site-fixed names in Strategist.** A local class that repeated the
rule let a reader that did not consult it ask for a hidden value. The rule is
on the type, so every reader gets the same answer.

# Anchor

`WDKBaseParameter.site_set` and `bindable` in veupathdb-py
`wdk/wdk_parameters.py`; `ParamGraph` in veupathdb-py
`domain/parameters/dependencies.py`; `ParameterInfo` in veupathdb-mcp
`catalog/param_formatting.py`; `SiteSetParameterError` in veupathdb-mcp
`catalog/site_set_params.py`; `PARAMETER_RULES` in
`services/strategies/parameter_rules.py`; `parameters_of_searches` and
`sheet_params_for_searches` in `services/strategies/sheet_params.py`;
`site_set_params_dropped` in `domain/strategy/spec_hydration.py`;
`published_parameters_of_searches` in `services/strategies/sheet_params.py`;
`diff_specs` in `domain/strategy/spec_diff.py`;
`isShown` and `isEditable` in `apps/web/src/lib/parameters/visibility.ts`.
