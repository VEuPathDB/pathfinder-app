---
type: Decision
title: A contextualized param view is an enrichment, and it has one owner
description: Six call sites asked WDK for a search's params under a context, with four exception types caught and five recoveries between them. The two with no policy at all are exactly where three separate bugs landed.
tags: [wdk-alignment, parameters, resilience, architecture]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-11-24T00:00:00Z }
status: stable
---

# What was decided

`get_search_params_under_context` owns the operation. It narrows a search's
parameters by a context when WDK can narrow them, returns `NotNarrowed` (the
static view and the site's refusal) when WDK cannot, and raises only when the
static view is unreachable too. Each caller states its policy: the binding walk
(`wdk_fetch_at`) reads the static view, and a reader that labels a held value
from the vocabulary under its parents (`wdk_fetch_under_parents_at`, used by
`sheet_params._sheet_under`) raises the refusal, so the step is `Unread` and the
turn is refused with the site's reason.

# Why: the seam had no owner

The same class of bug kept coming back, and an audit
proved it. One operation, six implementations:

| site | catches | recovery |
|---|---|---|
| `param_dag._wdk_fetch_at` | -- | **none** |
| `catalog_discovery.get_parameter_options` | -- | **none** |
| `param_validation._refresh_dependent_vocabularies` | `AppError` | static vocab |
| `wdk_conversion` | `AppError` | plain endpoint, else `None` |
| `plan_normalize` | `WDKError` | plain endpoint |
| `param_resolution` | `WDKError` | portal client, then static view |

The two with no policy are exactly where the day's bugs landed: parents not
filled before a refresh, a vocabulary read under WDK's defaults instead of the
bound parents, and a 5xx abandoning a criterion. Three symptoms, one missing
abstraction. Fixing them one at a time at their own call sites is why they
looked like an endless supply of new bugs.

# The principle that settles the policy

Contextualizing is an **enrichment**: it replaces a dependent param's static
vocabulary with the one valid under its parents. It is not a precondition for
the parent values being valid, and WDK does not treat it as one. Measured on
live PlasmoDB, `GenesByOrthologPattern`:

| call | result |
|---|---|
| refresh, `organism: ["Plasmodium falciparum 3D7"]` + `profile_pattern` | **500** |
| run, same values, gold parameter set | 200, `totalCount` a large result |

WDK returns 500 on the endpoint that narrows a vocabulary, for a value it
accepts and executes on the endpoint that runs the search. So losing the
narrowing costs vocabulary precision. It must never cost the search.

# What was deliberately left alone

- `param_validation` falls back through the **cached discovery service**, and
  integrations cannot depend on services. Same policy, different layer; it was
  already correct.
- `param_validation` above is the only one left alone.

`param_resolution` was originally in this list, on the reasoning that its portal
fallback answers a different question (this site versus the portal) rather than
"can WDK contextualize this". Both are true and neither replaces the other: the
portal retry asks another host the same question, and the host being asked is
not why WDK refused. Serving the step editor's parameter panel, that route
turned a refusal into a 500 and the panel reported the search as having no
parameters. It now tries the site, then the portal, then the static view, and
raises only when the static view fails too.

# Why a label does not fall back

A label read from the static view names a value from a vocabulary its parents
do not give, so the step shows a wrong label with nothing to say it is wrong.
The walk only binds, and the run endpoint checks what it binds; a label has no
such check. The cost is that a combination WDK refuses to narrow (below) refuses
the reading of a step that holds it.

# Evidence it works

Against the live 500, through the real client: one warning line
(`WDK could not contextualize search params; using the static view`) and all six
parameters returned, where the criterion previously died.


# The refusal is a combination, not a value

Measured on plasmodb.org against `GenesByOrthologPattern`: `organism` alone is
200, `profile_pattern` alone is 200, and `organism` together with any non-empty
`profile_pattern` is **500** - whether the pattern is well formed or not. The
static view of the same search is 200 throughout.

So a client cannot avoid this by validating values before it asks. Any policy
that treats a narrowing failure as fatal will fail on some combination of
otherwise valid values, which is why the fallback belongs in the operation
rather than at each call site.
