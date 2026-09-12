# PathFinder Dashboard Filters

SigNoz supports dashboard variables and dynamic filters in the UI. This guide names the most useful PathFinder dimensions so dashboards, alerts, and investigations all use the same vocabulary.

## Filter Glossary

### `site_host`

The VEuPathDB host serving a dependency request, such as plasmodb.org. Use this when latency or retries might be isolated to one site.

- Applies to: dependency-reliability

### `finish_reason`

How a turn ended, as the finish chunk reported it. Use this to separate turns that answered from turns that stopped or failed.

- Applies to: pipeline-overview

### `reason`

Why an event-stream subscription closed. Use this to tell a reader that left from a stream that reached its terminator.

- Applies to: streaming-delivery

### `kind`

The chunk kind of a frame served to a subscriber. Use this to see which part types dominate a stream.

- Applies to: streaming-delivery

## Dashboard Recommendations

### PathFinder Pipeline Overview

Assistant turn latency, throughput and token use, end to end.

- Recommended filters: `finish_reason`

### PathFinder Streaming Delivery

Live delivery health for SSE subscriptions and user-visible streaming behavior.

- Recommended filters: `reason`, `kind`, `resumed`

### PathFinder Dependency Reliability

External dependency health across WDK and site-search.

- Recommended filters: `site_host`, `endpoint_group`, `method`, `status_family`, `outcome`, `error_kind`

