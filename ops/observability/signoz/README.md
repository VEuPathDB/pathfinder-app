# PathFinder SigNoz Pack

This directory contains the PathFinder observability pack for SigNoz.

## Why This Exists

The SigNoz UI is still the place where operators view dashboards, inspect traces, and manage alerts. This pack simply makes the PathFinder-specific setup reproducible and reviewable instead of living only in someone's browser state.

The source of truth is intentionally vendor-neutral:

- [`pathfinder-observability-pack.json`](/Users/ahmedmuharram/repos/pathfinder/ops/observability/signoz/pathfinder-observability-pack.json)

Generated artifacts:

- importable dashboard JSON in [`dashboards/`](/Users/ahmedmuharram/repos/pathfinder/ops/observability/signoz/dashboards)
- alert catalog in [`alerts/`](/Users/ahmedmuharram/repos/pathfinder/ops/observability/signoz/alerts)
- filter guide in [`dashboard-filters.md`](/Users/ahmedmuharram/repos/pathfinder/ops/observability/signoz/dashboard-filters.md)
- live smoke test in [`../live_smoke_test.py`](/Users/ahmedmuharram/repos/pathfinder/ops/observability/live_smoke_test.py)

That split matters because the same source pack can be rendered and used across local, staging, production, and Cedar-hosted workflows instead of treating SigNoz UI state as the only source of truth.

## Refresh Artifacts

```bash
python3 ops/observability/signoz/render_pack.py
```

## Import Dashboards In SigNoz UI

1. Open SigNoz.
2. Go to `Dashboards`.
3. Choose `New Dashboard` then `Import JSON`.
4. Import the files from [`dashboards/`](/Users/ahmedmuharram/repos/pathfinder/ops/observability/signoz/dashboards).

If you are running the local observability stack, the dev overlay now bootstraps
the first SigNoz admin user via `/api/v1/register` using values from `.env.dev`:

- email: `SIGNOZ_ROOT_USER_EMAIL`
- password: `SIGNOZ_ROOT_USER_PASSWORD`

Recommended import order:

1. `pathfinder-pipeline-overview.json`
2. `pathfinder-approval-and-execution.json`
3. `pathfinder-streaming-delivery.json`
4. `pathfinder-dependency-reliability.json`

## Recommended Dashboard Filters

If you add SigNoz dashboard variables in the UI, start with the dimensions described in [`dashboard-filters.md`](/Users/ahmedmuharram/repos/pathfinder/ops/observability/signoz/dashboard-filters.md).

The most useful ones today are:

- `intent`: classified turn goal such as `new_strategy` or `follow_up`
- `model`: configured model for the turn or phase
- `surface`: user-facing workflow family such as `chat`, `plan_action`, or `workbench`
- `site_host`: target VEuPathDB host for dependency traffic

Those same dimensions are also reflected directly in several generated panels, so the dashboards stay useful even before anyone hand-configures UI variables.

## Run A Live Smoke Test

Use the local smoke test to verify that a real chat turn lands in both
Langfuse and SigNoz storage:

```bash
python3 ops/observability/live_smoke_test.py
```

The script:

- logs into the local mock API with `/api/v1/dev/login`
- starts a real `/api/v1/chat` turn and waits for `message_end`
- captures the emitted `traceId`
- verifies the trace in Langfuse ClickHouse
- verifies traces and metrics in SigNoz ClickHouse
- prints a filtered Docker log excerpt for the same run

## Alerts

Alert intent is version-controlled in:

- [`pathfinder-alert-catalog.json`](/Users/ahmedmuharram/repos/pathfinder/ops/observability/signoz/alerts/pathfinder-alert-catalog.json)
- [`pathfinder-alert-catalog.md`](/Users/ahmedmuharram/repos/pathfinder/ops/observability/signoz/alerts/pathfinder-alert-catalog.md)
- [`routing-strategy.md`](/Users/ahmedmuharram/repos/pathfinder/ops/observability/signoz/alerts/routing-strategy.md)

Why the catalog is not auto-applied yet:

- notification channels differ per environment
- on-call routing differs per team
- Cedar-hosted environments can differ from local and staging operations

So the thresholds, labels, and runbooks are the stable part, while final routing stays environment-owned.

## No Paid Services

Everything in this directory is designed for self-hosted/open-source workflows:

- SigNoz UI import
- source-controlled JSON and Markdown artifacts

No paid SaaS dependency is required.
