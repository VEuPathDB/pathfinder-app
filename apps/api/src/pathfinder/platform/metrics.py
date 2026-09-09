"""Application-level OTEL metric instruments.

Instruments are created eagerly on the global OTEL metrics API.  Before a
real ``MeterProvider`` is configured (via :func:`setup_observability`), they
record to a no-op sink.  Once the provider is set, the proxy instruments
forward to the real exporter automatically.

Defined in ``platform/`` so that every layer (integrations, services, AI)
can import without violating architecture boundaries.
"""

from opentelemetry import metrics

_pipeline_meter = metrics.get_meter("pathfinder.pipeline")
_sse_meter = metrics.get_meter("pathfinder.sse")

# ---------------------------------------------------------------------------
# Pipeline metrics
# ---------------------------------------------------------------------------

pipeline_runs = _pipeline_meter.create_counter(
    "pathfinder.pipeline.runs",
    description="Total pipeline runs by intent and outcome",
    unit="{run}",
)

pipeline_turn_duration_s = _pipeline_meter.create_histogram(
    "pathfinder.pipeline.turn_duration",
    description="Total wall-clock duration of each pipeline turn",
    unit="s",
)

pipeline_time_to_first_assistant_delta_s = _pipeline_meter.create_histogram(
    "pathfinder.pipeline.time_to_first_assistant_delta",
    description="Latency from turn start to the first assistant delta",
    unit="s",
)

pipeline_time_to_first_assistant_message_s = _pipeline_meter.create_histogram(
    "pathfinder.pipeline.time_to_first_assistant_message",
    description="Latency from turn start to the first complete assistant message chunk",
    unit="s",
)

pipeline_time_to_first_tool_call_s = _pipeline_meter.create_histogram(
    "pathfinder.pipeline.time_to_first_tool_call",
    description="Latency from turn start to the first tool call",
    unit="s",
)

pipeline_approval_wait_s = _pipeline_meter.create_histogram(
    "pathfinder.pipeline.approval_wait",
    description="Time spent waiting for user approval before execution resumes",
    unit="s",
)

pipeline_resume_after_approval_s = _pipeline_meter.create_histogram(
    "pathfinder.pipeline.resume_after_approval",
    description="Latency from approval to resumed pipeline activity",
    unit="s",
)

pipeline_execution_duration_s = _pipeline_meter.create_histogram(
    "pathfinder.pipeline.execution_duration",
    description="Duration of the execution phase inside a pipeline turn",
    unit="s",
)

pipeline_phase_events = _pipeline_meter.create_counter(
    "pathfinder.pipeline.phase_events",
    description="Lifecycle events emitted for each pipeline phase",
    unit="{event}",
)

phase_duration_s = _pipeline_meter.create_histogram(
    "pathfinder.pipeline.phase_duration",
    description="Duration of each pipeline phase",
    unit="s",
)

token_usage = _pipeline_meter.create_counter(
    "pathfinder.tokens.usage",
    description="Token consumption by model and type",
    unit="{token}",
)

pipeline_errors = _pipeline_meter.create_counter(
    "pathfinder.pipeline.errors",
    description="Pipeline errors by type and phase",
    unit="{error}",
)

pipeline_recoveries = _pipeline_meter.create_counter(
    "pathfinder.pipeline.recoveries",
    description="Recovered pipeline contract or orchestration issues by phase and kind",
    unit="{recovery}",
)

# ---------------------------------------------------------------------------
# SSE metrics
# ---------------------------------------------------------------------------

sse_subscriptions = _sse_meter.create_counter(
    "pathfinder.sse.subscriptions",
    description="SSE subscriptions opened by operation type and resume mode",
    unit="{subscription}",
)

sse_active_subscriptions = _sse_meter.create_up_down_counter(
    "pathfinder.sse.active_subscriptions",
    description="Current active SSE subscriptions",
    unit="{subscription}",
)

sse_subscription_duration_s = _sse_meter.create_histogram(
    "pathfinder.sse.subscription_duration",
    description="Lifetime of SSE subscriptions",
    unit="s",
)

sse_disconnects = _sse_meter.create_counter(
    "pathfinder.sse.disconnects",
    description="SSE subscription disconnects by reason",
    unit="{disconnect}",
)

sse_events_sent = _sse_meter.create_counter(
    "pathfinder.sse.events_sent",
    description="SSE events sent to subscribers by event type",
    unit="{event}",
)

sse_keepalives_sent = _sse_meter.create_counter(
    "pathfinder.sse.keepalives_sent",
    description="SSE keepalive comments sent to subscribers",
    unit="{keepalive}",
)
