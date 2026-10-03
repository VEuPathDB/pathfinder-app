---
type: Backlog
title: A search report sends a tree value as its leaves
description: veupathdb-py expands a countOnlyLeaves tree parent to its leaves when it creates a step, and sends it as it is in an anonymous search report; its retry error prints an empty message when the transport error has no text.
tags: [veupathdb-py, wdk, comparison, errors]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# A search report sends a tree value as its leaves

**What I did.** Read the two ways the client library sends one search
configuration to WDK, in `veupathdb-py` 0.1.0a19: a step
(`StrategyAPI.create_step`) and an anonymous report
(`VEuPathDBClient.run_search_report`, which a variant comparison runs).

**What I got.** `StepsMixin._prepare_parameters`
(`veupathdb/wdk/strategy_api/steps.py:137-151`) calls
`_expand_tree_params_to_leaves` (`strategy_api/base.py:82`), so a
`countOnlyLeaves` organism of `["Plasmodium"]` is sent as its leaves.
`run_search_report` (`veupathdb/wdk/_searches.py:138-168`) sends
`search_config` as it is. WDK answers the parent with 422 "organism: Number
of selected values (0) is not allowed". Separately, the retry path of
`_http.py:343` builds `f"Request failed after retries: {last}"`, and an
`httpx.ReadTimeout` prints as the empty string, so the error reads "Request
failed after retries: " with no cause.

**Why that's wrong.** One search configuration selects different genes by
the path that sends it, so every host that runs a report must repeat the
expansion. PathFinder does it in `ai/tools/standalone/_variant_targets.py`
with the canonicalizer the bind runs. The empty message leaves a host that
reports the site's words with nothing to say about a timeout; PathFinder names
the transport error class itself in `ai/capabilities/site_reads.py::site_words`.

**Fix.** In `veupathdb-py`: `run_search_report` expands tree parameters to
leaves through the same `_expand_tree_params_to_leaves` as `create_step`,
and the retry error names the exception class when its text is empty
(`f"{type(last).__name__}: {last}"`). Then PathFinder drops its own
expansion from `_variant_targets.py` and the class-name fallback from
`site_words`, in the change that takes the release.

**What you'd get.** A report and a step of the same configuration count the
same genes, and a timed-out request reads "Request failed after retries:
ReadTimeout".
