---
type: Backlog
title: An audit unit's stored message holds no raw error
description: A genome, finding or evidence unit that fails stores the text of the exception as its message, and the routes and the run page show it; store what the sanitized run halt stores, and keep the full error in the log.
tags: [audit, security]
generated: { by: claude-code/opus-5.5, at: 2026-11-03T00:00:00Z }
status: proposed
---

# An audit unit's stored message holds no raw error

## What happens

`UNIT_FAILURES` in `services/audit/units.py` holds `httpx.HTTPError` and `pydantic.ValidationError`. The handlers in `checks.py`, `confirm.py`, `collect.py`, `screen.py`, `tie_break.py` and `weighing.py` store `str(exc)` as the unit's message. An httpx message can name a request address with its query string, and a validation message can repeat its input. `GenomeView.message`, `FindingView.message` and `EvidenceView.message` send the text to the run and finding pages, outside any disclosure.

A run that halts already stores only the exception type and `sanitize_error_for_client(error)`.

## Done when

A failed unit stores a refusal's words and a generic sentence for anything else, the full error is in the log with the run bound, and a test holds an `httpx.HTTPStatusError` with a query string out of the stored row and the routes. The words the page needs for a site that did not answer stay plain.
