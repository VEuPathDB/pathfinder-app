---
type: Decision
title: The test suite runs with input screening off
description: PIGUARD_ENABLED is false for the whole suite and warm_up_scanner builds nothing when it is false, so no test loads the ONNX model whose telemetry thread aborts the process after the tests pass; a test about screening takes the piguard_enabled fixture. A process-wide atexit that releases the session, and onnxruntime 1.30.0, were both rejected on measurement.
tags: [testing, gates, piguard, onnxruntime, readiness]
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
status: stable
---

# What was decided

The test suite does not load the PIGuard ONNX model.

`apps/api/src/pathfinder/tests/conftest.py` sets `PIGUARD_ENABLED` to `false`
among the suite's environment defaults, and
`apps/api/src/pathfinder/ai/capabilities/security.py::warm_up_scanner` returns
without building the session when that setting is false, which is the setting
`scan_user_input` already read. A unit test that is about screening takes the
`piguard_enabled` fixture from `tests/unit/conftest.py`, so the model still
runs where the test is about the model. The default belongs to the root
conftest because a tier conftest may not write the process environment: the
tiers share one process, and
`test_no_tier_conftest_writes_the_process_environment` pins that.

No test feeds a real message through the model. The two tests that reach the
screening path replace the scanner, so the setting costs the suite no coverage.

# Why

The `onnxruntime` macOS wheel carries Microsoft's 1DS telemetry client inside
`onnxruntime_pybind11_state.so`. Building the session starts that client's
worker thread, and the thread outlives interpreter finalization: an HTTP reply
that lands after the C++ static destructors have destroyed the event source's
`recursive_mutex` makes `lock()` throw `system_error` on a thread with no
handler, and `std::terminate` aborts the process.

The abort lands after the summary line, so a tier in which every test passed
exits 134. Anything that reads the exit code, a pre-commit hook, a CI step, the
`&&` chain of the gate ladder, takes the tier as failed and never runs the
command after it. It is a race between the reply and static destruction, so the
rate moves with machine load.

# The readiness reading

A deployment that screens no input reports the `piguard` subsystem as ready, by
policy, and never as loaded. `ReadinessState` records one boolean per
subsystem and `/health/ready` answers 200 only when every one of them is ready,
so `not_ready` is the list of subsystems that hold traffic back. A subsystem the
deployment turned off holds nothing back, and reporting it not ready would leave
every screening-off deployment permanently 503. The probe says nothing about a
model being in memory, in either reading;
`test_a_disabled_piguard_is_ready_by_policy_and_loads_no_model` pins both halves:
the warm-up loads nothing, and the subsystem is ready with no error.

# What was rejected

**A process-wide `atexit` that releases the session.** Python's `atexit`
handlers run inside interpreter finalization, and the telemetry thread's pending
reply is not joined by session teardown, so a handler cannot order itself before
the library's own static destructors. It moves the race, it does not end it.

**`onnxruntime.disable_telemetry_events()` before the session is built.**
Measured: 1 abort in 10 runs against 2 in 10 at the same load. That is noise.

**`onnxruntime` 1.30.0, the newest release.** Measured on the transport tier
with the model loaded: 4 aborts in 8 runs, against 3 in 8 on the pinned 1.29.0
at the same load. The wheel still carries the telemetry client, so the version
in the lock is unchanged.

# What still aborts

The api process builds the session in its lifespan warm-up
(`apps/api/src/pathfinder/main.py`), which is the only place this application
builds it: `scan_user_input` has one caller, the chat dispatcher, and it runs in
the api process. So on a macOS developer machine that process can still abort at
exit. That is a process exit code after the work is done, not a test result, and
the Linux images are not reported affected. Upstream tracks it as
microsoft/onnxruntime issue 24579; the merged fix, PR 26445, is for the Node
binding.
