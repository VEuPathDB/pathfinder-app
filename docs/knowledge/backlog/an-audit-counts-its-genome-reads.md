---
type: Backlog
title: An audit counts its genome reads
description: veupathdb-py reports each WDK request to the observer and no JBrowse read, so an audit run's request counts leave out every genome window its checks read; the client gains a JBrowse hook and PathfinderObserver counts it into the same tally.
tags: [audit, observability, jbrowse, veupathdb-py]
generated: { by: claude-code/opus-5, at: 2026-10-22T00:00:00Z }
status: proposed
---

# An audit counts its genome reads

## What happens

Each audit stage counts the requests one unit sent with
`platform/metrics.py::counting_wdk_requests`, a tally that
`PathfinderObserver.on_wdk_request` fills, and stores the count on the stage
in `audit_runs.stages`. The client's `Observer` protocol
(`veupathdb-py: src/veupathdb/observer.py`) has hooks for WDK requests, their
retries, site search and the search line, and none for a JBrowse read. The
pseudogene, selenoprotein and length checks read genome windows from the
site's JBrowse store, so the run view states fewer requests than the run sent
to the site.

## Depends on

A `veupathdb-py` release whose JBrowse client reports each read to the
observer (an `on_jbrowse_request` hook beside `on_wdk_request`).

## Change

1. Take that release.
2. `PathfinderObserver` counts the JBrowse hook into the same tally, and
   exports it as its own series.
3. A test of each check stage asserts a count that includes the window reads.

## Done when

An audit run's stored request count equals the WDK requests plus the JBrowse
reads its units sent.
