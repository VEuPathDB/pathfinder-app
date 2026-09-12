---
type: Backlog
---

# The Lead reaches into private tool modules

**What I did.** Grepped `apps/api/src/pathfinder/ai/lead` and
`apps/api/src/pathfinder/ai/graph` for imports of a leading-underscore module of
`pathfinder.ai.tools.standalone`.

**What I got.** Five in `ai/lead`, none in `ai/graph`:

```
lead_tools.py:        _conversation_models.ClearStrategyResult, _workbench_models (3 names)
live_state.py:        _graph_helpers.build_step_response
sub_agent_dispatch.py: _stream_parts.graph_snapshot_chunk
edit_dispatch.py:     _strategy_refusals._wdk_refused_the_edit, _stream_parts.graph_snapshot_chunk
```

**Why that's wrong.** A leading underscore says the module is the tool package's
own business, so a rename inside `ai/tools/standalone` breaks the Lead. One of
the names, `_wdk_refused_the_edit`, is private twice over. The convention the
rest of the codebase keeps is that a shape two packages hold is declared where
both may read it: FRAME's `PinnedSheet` is in `ai/agents/state.py` and the tools
import it, and the EDA filter sheet is in `domain/eda_parts.py` for the same
reason.

**Why it happens.** Each name was written for one tool and then wanted by a
dispatch, and the import was the shortest route.

**Fix.** Give each name a home both packages may read: the result models to the
module that owns the concept (`ai/lead` for a Lead tool's result, the domain for
a shape the checkpoint holds), the chunk builders and the refusal reader to a
non-private module of the tool package. Then the rule is checkable: no module of
`ai/lead` or `ai/graph` imports `pathfinder.ai.tools.standalone._*`, which is
already asserted for `ai/graph/state.py` and `ai/lead/lead_pins.py` in
`tests/unit/ai/lead/test_pinned_eda_sheet.py`.

**What you'd get.** A rename inside the tool package stops being an outage in
the Lead, and one assertion covers both packages instead of two modules.
