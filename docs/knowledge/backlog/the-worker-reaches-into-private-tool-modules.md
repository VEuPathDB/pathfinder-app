---
type: Backlog
---

# The worker reaches into private tool modules

**What I did.** Grepped `apps/api/src/pathfinder/jobs` for imports of a
leading-underscore module of `pathfinder.ai.tools.standalone`, after the same
reads were removed from `ai/lead`.

**What I got.** Two:

```
jobs/impls/optimize_params_impl.py: _optimization_models.{OptimizationControls,
                                    OptimizationSettings, OptimizationTarget,
                                    _attach_export, _parse_and_validate_inputs}
jobs/impls/eda_compute_impl.py:     _eda_stream_parts.eda_analysis_state_chunk, .eda_viz_chunk
```

**Why that's wrong.** A leading underscore says the module is the tool
package's own business, so a rename inside `ai/tools/standalone` breaks the
worker, and a durable tool's worker-side body fails on an import rather than on
anything a researcher did. The two halves of a durable tool are declared
together everywhere else: the tool declaration, the agent-side tool and the
worker-side impl name one tool name.

**Why it happens.** Each shape was written for the agent-side tool and then
wanted by the impl that finishes the job, and the import was the shortest route.

**Fix.** Same shape as the Lead's: a name both halves of a durable tool read is
a declared surface, so `_optimization_models` and `_eda_stream_parts` become
non-private modules of the tool package, or the shape moves to the module that
owns the concept; `_attach_export` and `_parse_and_validate_inputs` lose their
own leading underscore too, because a name another package reads cannot be
private twice. Then widen
`tests/unit/ai/test_the_tool_package_declares_what_the_lead_reads.py` to
`pathfinder.jobs`, which holds the rule by construction for every reader
outside the tool package.

**What you'd get.** A rename inside the tool package stops being a durable-job
failure, and one assertion covers `ai/lead`, `ai/graph` and `jobs`.
