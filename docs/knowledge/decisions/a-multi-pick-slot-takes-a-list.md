---
type: Decision
title: A multi-pick slot takes a list
description: param_overrides was dict[str, str], so answering a multi-pick open slot with a list failed before any WDK call, and the model told the user WDK had rejected it.
tags: [agents, parameters, tool-surface]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# What happened

Answering a multi-pick open slot with the natural value produced:

```json
{"type": "string_type",
 "loc": ["param_overrides", "samples_percentile_generic"],
 "msg": "Input should be a valid string",
 "input": ["20 Hour", "21 Hour", "22 Hour", ...]}
```

`set_criterion(param_overrides: dict[str, str])` could not express a multi-value selection at all. The model retried with several encodings, then told the user "the API rejected the combined sample encoding" and offered to build 13 separate search arms.

WDK accepts that payload outright (a non-empty result). Nothing upstream had rejected anything -- the tool signature had.

# The change

The proposal map accepts a list per parameter. It is now `params: ParamProposals`, a `dict[str, str | list[str] | None]` whose `BeforeValidator` also reads a number or a JSON-encoded list.

The first version of this change also encoded the list to WDK wire form right there, via `_wire_overrides`. That half was wrong and has been reverted: encoding at the tool boundary made the whole serialized array one candidate option further down, so the model was told its own correct answer was invalid. The list now stays a list to the typed value. See [an-override-list-stays-a-list](an-override-list-stays-a-list.md).

# Why the shape matters more than the error

A multi-pick value *is* a list. Forcing the model to hand-encode it as a JSON string put the burden of the wire format on the caller, and when the caller got it wrong the failure surfaced as a Pydantic error the model could only interpret as an upstream rejection. That is how a tool-surface mismatch becomes a false report about someone else's API.

Same family as the left-folding `set_structure`: when a tool cannot say what the domain means, the model does not fail cleanly, it invents an explanation.

# What this did not fix

The DeRisi criterion still did not bind. With the list accepted, the failure moved one layer deeper twice more -- an unfilled parent param, then the wire encoding above -- before the criterion bound and the strategy built.

# Anchor

`params` on `set_criterion` in `ai/tools/standalone/frame_spec.py`. Guarded by `test_a_proposal_reaches_the_resolver_as_the_model_wrote_it` in `tests/unit/ai/tools/test_frame_proposals.py`.
