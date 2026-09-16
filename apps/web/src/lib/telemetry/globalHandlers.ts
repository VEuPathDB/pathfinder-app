/**
 * Wires window-level error sinks into the central `logError` channel.
 *
 * Five sinks run here (the React ErrorBoundary and AI SDK onError live next
 * to their consumers):
 *
 *   1. `window.onerror` - uncaught sync errors, script parse failures.
 *   2. `unhandledrejection` - promise rejections with no `.catch`.
 *   3. Capturing `error` listener - resource-load failures for img/script/
 *      link/css/font. These do NOT bubble so they're caught with
 *      `{capture: true}` at the window level.
 *   4. `PerformanceObserver({type: "longtask"})` - main-thread stalls >50ms.
 *      Logged at `warn` severity rather than full errors.
 *   5. Console.error interception - library warnings (React render warnings,
 *      third-party bugs logged without throwing) get forwarded once per
 *      unique message. Call sites that log real errors still get captured
 *      via their own throw path; this is just for the "screaming in the
 *      console, never thrown" category.
 *
 * Idempotent - safe to call multiple times.
 */

import { logError } from "./logError";

let installed = false;

export function installGlobalErrorHandlers(): void {
  if (installed) return;
  if (typeof window === "undefined") return;
  installed = true;

  window.addEventListener("error", (event) => {
    if (isResourceError(event)) {
      recordResourceError(event);
      return;
    }
    logError(event.error ?? event.message, {
      source: "global.onerror",
      route: currentRoute(),
      extra: {
        "error.filename": event.filename,
        "error.lineno": event.lineno,
        "error.colno": event.colno,
      },
    });
  });

  // Capture phase for resource-load errors that don't bubble.
  window.addEventListener(
    "error",
    (event) => {
      if (isResourceError(event)) {
        recordResourceError(event);
      }
    },
    true,
  );

  window.addEventListener("unhandledrejection", (event) => {
    logError(event.reason, {
      source: "global.unhandledrejection",
      route: currentRoute(),
    });
  });

  installLongTaskObserver();
  installConsoleErrorHook();
}

function isResourceError(event: ErrorEvent): boolean {
  return event.target instanceof Element && event.target !== document.body;
}

function recordResourceError(event: ErrorEvent): void {
  const target = event.target as Element;
  const tag = target.tagName.toLowerCase();
  const src = target.getAttribute("src") ?? target.getAttribute("href") ?? "unknown";
  logError(new Error(`resource load failed: <${tag}> ${src}`), {
    source: "global.resource",
    route: currentRoute(),
    extra: {
      "resource.tag": tag,
      "resource.src": src,
    },
  });
}

/**
 * PerformanceObserver captures main-thread tasks >50ms (default `longtask`
 * threshold). We emit each one as a low-severity `client.error` so patterns
 * of UI jank are visible in SigNoz.
 */
function installLongTaskObserver(): void {
  if (typeof PerformanceObserver === "undefined") return;
  try {
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const duration = Math.round(entry.duration);
        logError(new Error(`long task blocked main thread for ${String(duration)}ms`), {
          source: "global.longtask",
          route: currentRoute(),
          extra: {
            "longtask.duration_ms": duration,
            "longtask.name": entry.name,
            "longtask.start_ms": Math.round(entry.startTime),
          },
        });
      }
    });
    observer.observe({ type: "longtask", buffered: false });
  } catch {
    // Safari / Firefox may reject the entry type - silently skip.
  }
}

/**
 * Dedup the first ~200 unique messages logged via `console.error` so we
 * catch library warnings (React render warnings, deprecation notices) that
 * never raise. Call sites that log errors via logError() directly are NOT
 * affected - the hook calls the original console.error first so the
 * developer experience is unchanged.
 */
function installConsoleErrorHook(): void {
  const original = window.console.error.bind(window.console);
  const seen = new Set<string>();
  window.console.error = (...args: unknown[]) => {
    original(...args);
    if (seen.size >= 200) return;
    const message = stringifyArgs(args);
    if (seen.has(message)) return;
    seen.add(message);
    logError(new Error(`console.error: ${message}`), {
      source: "app",
      route: currentRoute(),
    });
  };
}

function stringifyArgs(args: readonly unknown[]): string {
  return args
    .map((a) => {
      if (typeof a === "string") return a;
      if (a instanceof Error) return a.message;
      try {
        return JSON.stringify(a);
      } catch {
        return "<unserializable>";
      }
    })
    .join(" ")
    .slice(0, 500);
}

function currentRoute(): string {
  return window.location.pathname;
}
