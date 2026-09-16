/**
 * Browser OpenTelemetry bootstrap.
 *
 * Wires a `WebTracerProvider` with:
 *   - Resource: `service.name = pathfinder-web`, `deployment.environment`,
 *     `session.id` (persisted via session.ts).
 *   - OTLP/HTTP exporter -> `/api/telemetry/v1/traces` (proxied to the SigNoz
 *     collector server-side; browser never speaks to the collector directly).
 *   - Batch span processor (1s schedule, up to 128 spans/export).
 *   - Zone.js context manager so async context survives microtasks in React
 *     19 + streaming fetch.
 *   - W3C Trace Context propagator (default) - `traceparent` headers are
 *     injected on fetches matching `propagateTraceHeaderCorsUrls`; backend
 *     already honors them.
 *
 * Auto-instrumentations + scrubbing:
 *   - FetchInstrumentation: configured with `ignoreUrls` so we never trace
 *     our own `/api/telemetry/*` proxy (infinite loop), and
 *     `applyCustomAttributesOnSpan` which strips query strings from
 *     `http.url` - the idiomatic OTel hook for attribute scrubbing before
 *     export.
 *   - XHR instrumentation: same ignoreUrls treatment.
 *   - DocumentLoad - one span per initial page load with full timing.
 *   - UserInteraction - click / submit / keydown spans.
 *
 * Idempotent: safe to call multiple times (second call returns early).
 * Gated on `NEXT_PUBLIC_TELEMETRY_ENABLED !== "false"`.
 */

import { trace, propagation, type Span } from "@opentelemetry/api";
import { W3CTraceContextPropagator } from "@opentelemetry/core";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { registerInstrumentations } from "@opentelemetry/instrumentation";
import { DocumentLoadInstrumentation } from "@opentelemetry/instrumentation-document-load";
import { FetchInstrumentation } from "@opentelemetry/instrumentation-fetch";
import { UserInteractionInstrumentation } from "@opentelemetry/instrumentation-user-interaction";
import { XMLHttpRequestInstrumentation } from "@opentelemetry/instrumentation-xml-http-request";
import { resourceFromAttributes } from "@opentelemetry/resources";
import { BatchSpanProcessor, WebTracerProvider } from "@opentelemetry/sdk-trace-web";
import { ZoneContextManager } from "@opentelemetry/context-zone";
import { ATTR_SERVICE_NAME } from "@opentelemetry/semantic-conventions";

import { getOrCreateSessionId } from "./session";

const SERVICE_NAME = "pathfinder-web";
const TRACES_ENDPOINT = "/api/telemetry/v1/traces";

const TELEMETRY_SELF_URL_RE = /\/api\/telemetry\//;
const PROPAGATE_API_URL_RE = /\/api\//;

let initialized = false;

export function initTelemetry(): void {
  if (initialized) return;
  if (typeof window === "undefined") return;
  if (process.env["NEXT_PUBLIC_TELEMETRY_ENABLED"] === "false") return;

  initialized = true;

  const deploymentEnv = process.env["NEXT_PUBLIC_DEPLOYMENT_ENV"] ?? "development";
  const sessionId = getOrCreateSessionId();

  const resource = resourceFromAttributes({
    [ATTR_SERVICE_NAME]: SERVICE_NAME,
    "deployment.environment": deploymentEnv,
    "session.id": sessionId,
    "telemetry.sdk.language": "webjs",
  });

  const exporter = new OTLPTraceExporter({
    url: TRACES_ENDPOINT,
  });

  const provider = new WebTracerProvider({
    resource,
    spanProcessors: [
      new BatchSpanProcessor(exporter, {
        scheduledDelayMillis: 1000,
        maxExportBatchSize: 128,
        maxQueueSize: 512,
      }),
    ],
  });

  provider.register({
    contextManager: new ZoneContextManager(),
    propagator: new W3CTraceContextPropagator(),
  });

  propagation.setGlobalPropagator(new W3CTraceContextPropagator());

  registerInstrumentations({
    tracerProvider: provider,
    instrumentations: [
      new DocumentLoadInstrumentation(),
      new UserInteractionInstrumentation({
        eventNames: ["click", "submit", "keydown"],
      }),
      new FetchInstrumentation({
        propagateTraceHeaderCorsUrls: [PROPAGATE_API_URL_RE],
        ignoreUrls: [TELEMETRY_SELF_URL_RE],
        clearTimingResources: true,
        applyCustomAttributesOnSpan: sanitizeFetchSpan,
      }),
      new XMLHttpRequestInstrumentation({
        propagateTraceHeaderCorsUrls: [PROPAGATE_API_URL_RE],
        ignoreUrls: [TELEMETRY_SELF_URL_RE],
        applyCustomAttributesOnSpan: sanitizeXhrSpan,
      }),
    ],
  });

  trace.setGlobalTracerProvider(provider);
}

/**
 * Runs right before the fetch span closes. Strips query strings from
 * `http.url` - we never want tokens / user ids / session keys to reach the
 * collector, and request bodies are never captured by fetch instrumentation
 * in the first place.
 */
function sanitizeFetchSpan(
  span: Span,
  request: Request | RequestInit,
  result: Response | FetchError,
): void {
  const url = extractFetchUrl(request, result);
  if (url !== undefined) {
    span.setAttribute("http.url", stripQuery(url));
  }
}

function sanitizeXhrSpan(span: Span, xhr: XMLHttpRequest): void {
  const url = xhr.responseURL;
  if (url.length > 0) {
    span.setAttribute("http.url", stripQuery(url));
  }
}

interface FetchError {
  readonly status?: number;
  readonly message?: string;
}

function extractFetchUrl(
  request: Request | RequestInit,
  result: Response | FetchError,
): string | undefined {
  if (result instanceof Response && result.url.length > 0) return result.url;
  if (request instanceof Request) return request.url;
  return undefined;
}

function stripQuery(url: string): string {
  const q = url.indexOf("?");
  return q === -1 ? url : url.slice(0, q);
}
