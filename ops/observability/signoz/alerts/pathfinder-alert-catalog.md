# PathFinder Alert Catalog

This catalog is the reviewed source of truth for alert intent, thresholds, labels, and runbooks.

Today:
- Use these definitions to create SigNoz alerts in the UI.
- Keep routing/channel details environment-specific.
- Reuse the same metadata across local, staging, production, and Cedar-hosted workflows.

## 1. High Turn Latency

- `slug`: `high-turn-latency-warning`
- `severity`: `warning`
- `signal`: `metrics`
- `metric`: `pathfinder.pipeline.turn_duration`
- `operator`: `p95 above 30 s`
- `for`: `10m`
- `evaluateEvery`: `1m`
- `labels`: `{"class": "latency", "surface": "pipeline", "team": "pathfinder"}`
- `summary`: PathFinder p95 turn latency is elevated.
- `description`: Investigate model/provider slowness, WDK latency, site-search latency, and Redis stream health. Correlate with SSE and dependency dashboards before assuming the model is the only cause.
- `runbook`: Check Pipeline Overview, Streaming Delivery, and Dependency Reliability dashboards together.

## 2. Slow First Assistant Delta

- `slug`: `slow-first-token-warning`
- `severity`: `warning`
- `signal`: `metrics`
- `metric`: `pathfinder.pipeline.time_to_first_assistant_delta`
- `operator`: `p95 above 8 s`
- `for`: `10m`
- `evaluateEvery`: `1m`
- `labels`: `{"class": "latency", "surface": "streaming", "team": "pathfinder"}`
- `summary`: Users are waiting too long for the first visible assistant output.
- `description`: Use this to catch degraded user-perceived responsiveness before total turn duration becomes extreme.
- `runbook`: Compare time-to-first-delta against time-to-first-tool-call and dependency latency.

## 3. Pipeline Error Spike

- `slug`: `pipeline-errors-critical`
- `severity`: `critical`
- `signal`: `metrics`
- `metric`: `pathfinder.pipeline.errors`
- `operator`: `rate above 0.05 errors/s`
- `for`: `5m`
- `evaluateEvery`: `1m`
- `labels`: `{"class": "availability", "surface": "pipeline", "team": "pathfinder"}`
- `summary`: Pipeline errors are occurring at a critical rate.
- `description`: A sustained error rate usually means broken orchestration, dependency failures, or state-machine regressions that are directly user-visible.
- `runbook`: Check Pipeline Error traces, phase failure context, and the Dependency Reliability dashboard.

## 4. Recovery Spike

- `slug`: `recovery-spike-warning`
- `severity`: `warning`
- `signal`: `metrics`
- `metric`: `pathfinder.pipeline.recoveries`
- `operator`: `rate above 0.03 recoveries/s`
- `for`: `15m`
- `evaluateEvery`: `1m`
- `labels`: `{"class": "degradation", "surface": "pipeline", "team": "pathfinder"}`
- `summary`: Recovery paths are activating unusually often.
- `description`: Not every recovery is user-visible, but a spike often signals prompt drift, contract drift, or dependency instability before outright failures.
- `runbook`: Inspect recovery kinds by phase and compare against recent deploys or prompt changes.

## 5. Approval Wait Elevated

- `slug`: `approval-wait-warning`
- `severity`: `warning`
- `signal`: `metrics`
- `metric`: `pathfinder.pipeline.approval_wait`
- `operator`: `p95 above 120 s`
- `for`: `30m`
- `evaluateEvery`: `5m`
- `labels`: `{"class": "ux", "surface": "approval", "team": "pathfinder"}`
- `summary`: Users are taking unusually long to approve plans.
- `description`: This can indicate confusing plans, overloaded plan cards, or an approval UX that is not inspiring confidence.
- `runbook`: Check plan presentation quality in Langfuse and compare with approval funnel metrics.

## 6. SSE Disconnect Spike

- `slug`: `sse-disconnect-spike-warning`
- `severity`: `warning`
- `signal`: `metrics`
- `metric`: `pathfinder.sse.disconnects`
- `operator`: `rate above 0.1 disconnects/s`
- `for`: `10m`
- `evaluateEvery`: `1m`
- `labels`: `{"class": "delivery", "surface": "sse", "team": "pathfinder"}`
- `summary`: SSE disconnects are elevated.
- `description`: High disconnect rates can degrade the user experience even when the backend eventually completes the turn.
- `runbook`: Check disconnect reasons, active subscription levels, and Redis stream emit latency.

## 7. Redis Stream Emit Latency Elevated

- `slug`: `redis-stream-latency-warning`
- `severity`: `warning`
- `signal`: `metrics`
- `metric`: `pathfinder.redis.stream_emit_duration`
- `operator`: `p95 above 0.25 s`
- `for`: `10m`
- `evaluateEvery`: `1m`
- `labels`: `{"class": "backplane", "surface": "redis", "team": "pathfinder"}`
- `summary`: Redis Stream appends are slower than expected.
- `description`: Backplane slowness can surface as delayed streaming, stuck UIs, and poor transcript pacing.
- `runbook`: Inspect Redis latency, stream emit attempts, and SSE event send rate.

## 8. WDK Latency Elevated

- `slug`: `wdk-latency-warning`
- `severity`: `warning`
- `signal`: `metrics`
- `metric`: `veupathdb.wdk.request_duration`
- `operator`: `p95 above 5 s`
- `for`: `10m`
- `evaluateEvery`: `1m`
- `labels`: `{"class": "dependency", "surface": "wdk", "team": "pathfinder"}`
- `summary`: WDK request latency is elevated.
- `description`: Discovery and execution both depend on WDK responsiveness; sustained latency here will directly affect turn duration and verification time.
- `runbook`: Check WDK request duration, retries, and site host distribution.

## 9. WDK Retry Spike

- `slug`: `wdk-retry-spike-critical`
- `severity`: `critical`
- `signal`: `metrics`
- `metric`: `veupathdb.wdk.request_retries`
- `operator`: `rate above 0.1 retries/s`
- `for`: `10m`
- `evaluateEvery`: `1m`
- `labels`: `{"class": "dependency", "surface": "wdk", "team": "pathfinder"}`
- `summary`: WDK retries are spiking.
- `description`: Retry spikes often precede user-visible failures and indicate upstream instability, network issues, or endpoint-specific trouble.
- `runbook`: Pivot by endpoint group and site host; inspect WDK failure traces.

## 10. Site Search Latency Elevated

- `slug`: `site-search-latency-warning`
- `severity`: `warning`
- `signal`: `metrics`
- `metric`: `veupathdb.site_search.request_duration`
- `operator`: `p95 above 3 s`
- `for`: `10m`
- `evaluateEvery`: `1m`
- `labels`: `{"class": "dependency", "surface": "site-search", "team": "pathfinder"}`
- `summary`: Site-search latency is elevated.
- `description`: Discovery can feel stalled long before WDK itself is unhealthy if site-search slows down.
- `runbook`: Compare site-search latency and retries with discovery phase duration.

