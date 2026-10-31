---
type: Backlog
title: A strategy read in the tool server waits in its line
description: The control tests in veupathdb_mcp.controls read the step's WDK strategy inside the library, outside the strategy line PathFinder holds around its own strategy requests, so a canvas edit during a control-test task can still be undone by that read; give veupathdb-py a host-installed gate for every strategy request, install the line there, and drop the call-site wraps.
tags: [wdk, strategy, veupathdb-py, veupathdb-mcp, controls]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: proposed
---

# A strategy read in the tool server waits in its line

## What happens

A WDK strategy read saves the strategy back, so PathFinder holds the strategy's line around
every strategy request it sends
([the decision](../decisions/a-request-on-a-wdk-strategy-waits-in-its-line.md)).
`veupathdb_mcp/controls/control_tests.py::_copied_subtree` reads the strategy of the step
under test with `api.get_strategy` inside the library. A control-test, optimization or
separation task runs while the turn is parked, and `/operations` does not refuse a canvas
edit while a task runs, so that read can overlap a canvas step-tree write. The read after
the write then fails the edit with `TreeNotHeldError`; the stored strategy and the site
agree, but the researcher sees a refused edit.

## Done when

`veupathdb-py` passes every request on a strategy (`GET`, `PATCH` and `DELETE` of
`/users/{id}/strategies/{id}` and `PUT .../step-tree`) through a gate the host installs,
with the strategy id; PathFinder installs `held_strategy` as that gate in the api and the
worker; the `async with held_strategy(...)` wraps and their source sweep test are removed;
`veupathdb-py` and `veupathdb-mcp` are released and both pins taken.
