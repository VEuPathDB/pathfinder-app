/**
 * Central error sink - every error path in the app (global onerror,
 * unhandledrejection, resource-load listeners, React ErrorBoundary, AI SDK
 * onError, try/catch call sites) funnels here.
 *
 * Creates a short-lived span named `client.error` with the source tagged via
 * `error.source`, attaches the full exception via the OTel recordException
 * API (stack + type + message), and ends it. SigNoz's Exceptions view groups
 * these automatically by service + exception.type.
 *
 * No request / response bodies are ever captured - only stack, URL, route,
 * session.id, and whatever caller context the call site provides. A
 * best-effort scrub strips anything that looks like a bearer token.
 */

import { trace, SpanStatusCode, type Attributes } from "@opentelemetry/api";

const TRACER_NAME = "pathfinder-web/errors";

export type ErrorSource =
  | "global.onerror"
  | "global.unhandledrejection"
  | "global.resource"
  | "global.longtask"
  | "react.errorBoundary"
  | "ai.useChat"
  | "app";

export interface LogErrorContext {
  readonly source: ErrorSource;
  readonly route?: string;
  readonly component?: string;
  /** Any extra key/value context relevant to the error. */
  readonly extra?: Readonly<Record<string, string | number | boolean>>;
}

export function logError(error: unknown, context: LogErrorContext): void {
  if (typeof window === "undefined") return;
  const err = toError(error);
  const tracer = trace.getTracer(TRACER_NAME);
  const span = tracer.startSpan("client.error", {
    attributes: buildAttributes(context),
  });
  span.setStatus({ code: SpanStatusCode.ERROR, message: err.message });
  span.recordException(err);
  span.end();
}

function buildAttributes(context: LogErrorContext): Attributes {
  const attrs: Attributes = {
    "error.source": context.source,
  };
  if (context.route !== undefined) attrs["client.route"] = context.route;
  if (context.component !== undefined) attrs["client.component"] = context.component;
  if (typeof window !== "undefined") {
    attrs["client.url"] = scrub(window.location.href);
    attrs["client.viewport.width"] = window.innerWidth;
    attrs["client.viewport.height"] = window.innerHeight;
  }
  if (context.extra !== undefined) {
    for (const [key, value] of Object.entries(context.extra)) {
      attrs[`client.${key}`] = value;
    }
  }
  return attrs;
}

function toError(value: unknown): Error {
  if (value instanceof Error) return value;
  if (typeof value === "string") return new Error(scrub(value));
  try {
    return new Error(scrub(JSON.stringify(value)));
  } catch {
    return new Error("non-serializable error");
  }
}

/** Redact anything that looks like a bearer token in an error message. */
function scrub(text: string): string {
  return text
    .replace(/Bearer\s+[A-Za-z0-9._-]+/gi, "Bearer <redacted>")
    .replace(/api[_-]?key=[^&\s]+/gi, "api_key=<redacted>");
}
