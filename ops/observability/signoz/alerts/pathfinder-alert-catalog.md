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
- `metric`: `assistant.turn.duration`
- `operator`: `p95 above 30 s`
- `for`: `10m`
- `evaluateEvery`: `1m`
- `labels`: `{"class": "latency", "surface": "pipeline", "team": "pathfinder"}`
- `summary`: PathFinder p95 turn latency is elevated.
- `description`: Investigate model or provider slowness, WDK latency and site-search latency. Correlate with the streaming and dependency dashboards before assuming the model is the only cause.
- `runbook`: Check Pipeline Overview, Streaming Delivery, and Dependency Reliability dashboards together.

## 2. Slow First Assistant Delta

- `slug`: `slow-first-token-warning`
- `severity`: `warning`
- `signal`: `metrics`
- `metric`: `assistant.turn.time_to_first_delta`
- `operator`: `p95 above 8 s`
- `for`: `10m`
- `evaluateEvery`: `1m`
- `labels`: `{"class": "latency", "surface": "streaming", "team": "pathfinder"}`
- `summary`: Users are waiting too long for the first visible assistant output.
- `description`: Use this to catch degraded user-perceived responsiveness before total turn duration becomes extreme.
- `runbook`: Compare time-to-first-delta against time-to-first-tool-call and dependency latency.

## 3. SSE Disconnect Spike

- `slug`: `sse-disconnect-spike-warning`
- `severity`: `warning`
- `signal`: `metrics`
- `metric`: `assistant.sse.disconnects`
- `operator`: `rate above 0.1 disconnects/s`
- `for`: `10m`
- `evaluateEvery`: `1m`
- `labels`: `{"class": "delivery", "surface": "sse", "team": "pathfinder"}`
- `summary`: SSE disconnects are elevated.
- `description`: High disconnect rates can degrade the user experience even when the backend eventually completes the turn.
- `runbook`: Check disconnect reasons, active subscription levels, and Redis stream emit latency.

## 4. WDK Latency Elevated

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

## 5. WDK Retry Spike

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

## 6. Site Search Latency Elevated

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

