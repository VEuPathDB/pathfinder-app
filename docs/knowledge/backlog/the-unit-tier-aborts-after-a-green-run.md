---
type: Backlog
title: The unit tier aborts with exit 134 after a green run
description: The telemetry thread ONNX Runtime starts when the PIGuard model loads aborts the pytest process after the tests pass, so a run in which every test passed reports failure to anything that reads the exit code.
tags: [tests, gates, piguard, onnxruntime]
status: open
---

# The unit tier aborts with exit 134 after a green run

## What I did

Ran `uv run pytest src/pathfinder/tests/unit/transport -q` from `apps/api` eight times
in a row on an idle machine, recording the shell exit code of each run. Ran the same
command six times with `PIGUARD_ENABLED=false`.

## What I got

The suite passes and the process aborts:

```
106 passed, 15 warnings in 6.37s
libc++abi: terminating due to uncaught exception of type
std::__1::system_error: recursive_mutex lock failed: Invalid argument
```

Exit 134, SIGABRT, on 5 of the 8 runs, each time after pytest printed `106 passed`.
With `PIGUARD_ENABLED=false`: exit 0 on 6 of 6 runs. The macOS crash report of an
aborted run names the faulting thread as ONNX Runtime's 1DS telemetry `WorkerThread`,
which dispatches an HTTP response into `DebugEventSource` and locks a `recursive_mutex`
that interpreter finalization already destroyed.

## Why that's wrong

The run prints `106 passed` and the shell sees 134. Every reader of the exit code, a
pre-commit hook, a CI step, the `&&` chain of the gate ladder, a developer's shell,
takes the whole tier as failed on a run in which every test passed, and the next
command in the chain never runs. The same stack shows the unit tier making an outbound
HTTP call that the tier's socket guard cannot see, because this client is native.

## Why it happens

The `onnxruntime` 1.29.0 macOS wheel carries Microsoft's 1DS telemetry client inside
`onnxruntime_pybind11_state.so`. Loading the PIGuard model starts that client's
`WorkerThread`, and the thread outlives interpreter finalization: a reply that lands
after the C++ static destructors have destroyed `DebugEventSource`'s `recursive_mutex`
makes `lock()` throw `system_error`, nothing on that thread catches it, and
`std::terminate` aborts the process. It is a race between the reply and static
destruction, so the rate moves with machine load.

## Fix

The remedy belongs where the ONNX session is built,
`assistant-platform: packages/assistant-core/src/assistant_core/capabilities/piguard.py`,
which this repository cannot edit: release the InferenceSession before interpreter
finalization, or take an `onnxruntime` build without the telemetry client. One
candidate is measured and is not the remedy: `onnxruntime.disable_telemetry_events()`
before the session is built gives 1 abort in 10 runs against 2 in 10 at the same load.

PathFinder's part is the load. `Settings.piguard_enabled` defaults to true
(`apps/api/src/pathfinder/platform/config.py`), the module-level `UserInputScanner` in
`apps/api/src/pathfinder/ai/capabilities/security.py` names the model directory, and the
session-scoped autouse fixture `_warm_the_input_scanner` in
`apps/api/src/pathfinder/tests/conftest.py` loads the model for every test session that
reads those settings. The alternative to a platform fix is that the unit tier does not
load PIGuard at all.

## What you'd get

`uv run pytest src/pathfinder/tests/unit -q` exits 0 on every run, so the `&&` chain in
the gate ladder reaches the command after it, and the unit tier makes no outbound HTTP
call.
