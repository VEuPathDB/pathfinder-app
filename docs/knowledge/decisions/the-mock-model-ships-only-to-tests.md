---
type: Decision
title: The mock model ships only to tests
description: The scripted model, the audit mock, the scripted injection judge, and the no-decision transport live in strategist_scripted, a package beside strategist that only the test environment and the e2e image stage contain. Production reaches it by name through one seam, and a mock deployment without it fails at boot. A uv workspace member, a plugin registry, readers fed through the scripted model, and moving it under tests/ were rejected.
tags: [mock, e2e, docker, import-linter, gates]
generated: { by: claude-code/opus-5, at: 2026-11-23T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-11-23T00:00:00Z }
status: stable
---

# What was decided

`apps/api/src/strategist_scripted/` holds every stand-in a mock deployment runs
instead of a provider: Strategist's script (`models/`), the audit assistant's
auditor, reviewer and synthesis (`audit/`), the injection judge (`judge.py`)
and the no-decision transport (`decisions.py`), and the curated seed strategies
those scripts bind their values from (`seeds/`: the catalog, the JSON per site, the
organism marks and their recorder, `python -m strategist_scripted.seeds`), and the
routes only a mock deployment mounts (`dev_routes.py`: the dev login and the
sample audit run, with `audit/sample_run.py` and its JSON). It sits in the same source root
as `strategist`, so the editable install puts it on the test environment's path,
but the wheel names only `src/strategist`.

Production reaches it through `strategist/ai/scripted.py`: `scripted()` imports
the package by the name `platform/config.py::SCRIPTED_PACKAGE` holds and returns
its `SCRIPTED`, one `ScriptedDeployment` record. Every call sits behind
`is_mock_deployment()`; `create_app` mounts `SCRIPTED.dev_router` only there.
The OpenAPI generator refuses any path under `DEV_ROUTE_PREFIX`, so it reads no
scripted router. `Settings` refuses `STRATEGIST_CHAT_PROVIDER=mock` when
the package is not importable, so the api, the worker and the devtools fail at
boot, never on a turn.

`apps/api/Dockerfile` builds a `runtime` stage that copies `src/strategist`
only, an `e2e` stage that adds `src/strategist_scripted`, and ends on
`FROM runtime`, so a build that names no target ships no scripted model.

# What enforces it

- import-linter: production `strategist` never imports `strategist_scripted`
  (the tests are exempt), and `strategist_scripted` never imports
  `strategist.tests`, which the image deletes.
- `tests/unit/test_only_the_seam_names_the_scripted_package.py`: only
  `platform/config.py` names the package, because import-linter cannot see an
  import by name.
- `tests/unit/test_the_production_image_ships_no_scripted_model.py`: the stages
  of the Dockerfile and the targets compose and CI build.

# What stays in production

The switch, not the double: `is_mock_deployment()` and its readers, the
`mock:deterministic` catalog entry, the title generator's mock factory
parameter, and `ai/lead/scripted_scope.py`, which sets the two context vars
`assistant_core.models.scripted` defines for a runner. The intent, route and
operator readers keep a one-line branch each.

# Rejected

- **A uv workspace member or a second distribution.** Nothing builds a wheel of
  the package; a pyproject, a lock entry and an install step in the e2e stage
  buy nothing over a second directory in the same source root.
- **A plugin registry with an `install()` hook called by the api and the
  worker.** Every use is lazy and behind one setting, so one import by name and
  one check in `Settings` are the whole mechanism.
- **Feeding the readers through the scripted model or the Decisions
  transport.** The scripted intent and operator answers read the turn's state
  (the arc from earlier words, an answered card), which neither the message
  reader's prompt nor a decision request carries; carrying it would change
  production requests for the double's sake.
- **Moving the mock under `tests/`.** The image deletes the tests, and the e2e
  stack and the devtools' `--mock` run need the double inside an image.
