import { z } from "zod";

import { getConfiguredServerApiBaseUrl } from "@/lib/config/apiBase";

export class SchemaValidationError extends Error {
  url: string;
  issues: unknown[];

  constructor(url: string, issues: unknown[]) {
    const summary = issues
      .slice(0, 3)
      .map((i) =>
        typeof i === "object" && i && "message" in i
          ? String((i as { message: string }).message)
          : String(i),
      )
      .join("; ");
    super(`API response validation failed for ${url}: ${summary}`);
    this.name = "SchemaValidationError";
    this.url = url;
    this.issues = issues;
  }
}

export class APIError extends Error {
  status: number;
  statusText: string;
  url: string;
  data: unknown;

  constructor(
    message: string,
    args: { status: number; statusText: string; url: string; data: unknown },
  ) {
    super(message);
    this.name = "APIError";
    this.status = args.status;
    this.statusText = args.statusText;
    this.url = args.url;
    this.data = args.data;
  }
}

function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    // In the browser, use the page's own origin so every request goes through
    // the Next.js rewrite proxy (configured in next.config.js).  This keeps
    // cookies on the same origin as the page, avoiding cross-origin cookie
    // issues that cause "different session" errors when the API runs on a
    // different port (e.g. localhost:3000 → localhost:8000).
    return window.location.origin;
  }
  // Server-side (SSR / route handlers): reach the API directly.
  return getConfiguredServerApiBaseUrl();
}

export function buildUrl(path: string, query?: Record<string, unknown>): string {
  const base = getApiBaseUrl();
  const url =
    path.startsWith("http://") || path.startsWith("https://")
      ? new URL(path)
      : new URL(path, base);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null) continue;
      url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

export function getAuthHeaders(opts?: {
  accept?: string;
  contentType?: string;
  extra?: Record<string, string>;
}): Record<string, string> {
  return {
    "X-Requested-With": "XMLHttpRequest",
    ...(opts?.accept != null && opts.accept !== "" ? { Accept: opts.accept } : {}),
    ...(opts?.contentType != null && opts.contentType !== ""
      ? { "Content-Type": opts.contentType }
      : {}),
    ...(opts?.extra ?? {}),
  };
}

export async function parseResponseBody(resp: Response): Promise<unknown> {
  const contentType = resp.headers.get("content-type") ?? "";
  if (contentType.includes("json")) {
    try {
      return await resp.json();
    } catch {
      return null;
    }
  }
  try {
    return await resp.text();
  } catch {
    return null;
  }
}

type RequestArgs = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Record<string, string | number | boolean | null | undefined>;
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
};

/**
 * An error body the API can send: an RFC 7807 problem, a FastAPI validation
 * payload, or a problem that carries one entry per refused field. Every member
 * is read on its own, so a member this reader cannot use costs only itself.
 */
const errorBodySchema = z.looseObject({
  detail: z.unknown().optional(),
  title: z.unknown().optional(),
  errors: z.unknown().optional(),
});

/** One refused field, in either the FastAPI shape or the problem shape. */
const fieldIssueSchema = z.looseObject({
  msg: z.string().optional(),
  message: z.string().optional(),
  loc: z.array(z.unknown()).optional(),
  path: z.string().optional(),
});

type FieldIssue = z.infer<typeof fieldIssueSchema>;

/** Parts of a FastAPI location that name where a value came from, not which one. */
const REQUEST_PARTS = new Set(["body", "query", "path", "header", "cookie"]);

/** The most the reader hands a caller, so a form with many refused fields fits. */
const MESSAGE_LIMIT = 300;

function nonEmpty(value: string | null | undefined): string | null {
  return value == null || value.trim() === "" ? null : value;
}

function issues(entries: unknown): FieldIssue[] {
  if (!Array.isArray(entries)) return [];
  const parsed = entries.map((entry) => fieldIssueSchema.safeParse(entry));
  return parsed.filter((one) => one.success).map((one) => one.data);
}

function sentenceOf(issue: FieldIssue): string | null {
  return nonEmpty(issue.msg ?? issue.message);
}

/** The field a located refusal is about: the name it declares, else its location. */
function locatedField(issue: FieldIssue): string | null {
  const declared = nonEmpty(issue.path);
  if (declared !== null) return declared;
  const named = (issue.loc ?? []).filter(
    (part): part is string => typeof part === "string" && !REQUEST_PARTS.has(part),
  );
  return named.at(-1) ?? null;
}

function joinWithinLimit(sentences: string[]): string | null {
  const first = sentences.at(0);
  if (first === undefined) return null;
  const whole = sentences.join("; ");
  if (whole.length <= MESSAGE_LIMIT) return whole;
  const kept: string[] = [];
  let width = 0;
  for (const sentence of sentences) {
    if (width + sentence.length + 2 > MESSAGE_LIMIT) break;
    kept.push(sentence);
    width += sentence.length + 2;
  }
  const shown = kept.length === 0 ? [first.slice(0, MESSAGE_LIMIT)] : kept;
  const hidden = sentences.length - shown.length;
  return hidden === 0 ? shown.join("; ") : `${shown.join("; ")} (+${hidden} more)`;
}

/** Refusals that carry a location, whose field name is the only subject they have. */
function locatedMessage(entries: unknown): string | null {
  const located = issues(entries).filter((issue) => issue.loc !== undefined);
  if (located.length === 0) return null;
  const sentences: string[] = [];
  for (const issue of located) {
    const text = sentenceOf(issue);
    if (text === null) continue;
    const field = locatedField(issue);
    sentences.push(field === null ? text : `${field}: ${text}`);
  }
  return joinWithinLimit(sentences);
}

/** Refusals that write their own sentence, which already names its subject. */
function writtenMessage(entries: unknown): string | null {
  const sentences: string[] = [];
  for (const issue of issues(entries)) {
    const text = sentenceOf(issue);
    if (text !== null) sentences.push(text);
  }
  return joinWithinLimit(sentences);
}

/** A detail says something only when it is a sentence or a list of refusals. */
function detailMessage(detail: unknown): string | null {
  if (typeof detail === "string") return nonEmpty(detail);
  if (Array.isArray(detail)) return locatedMessage(detail) ?? writtenMessage(detail);
  return null;
}

/** The sentence the server offers about a refusal, or null when it offers none.
 *
 * A located refusal carries its subject only in that location, so it is read
 * first; a refusal that writes its own sentence defers to the summary.
 */
export function extractErrorMessage(data: unknown): string | null {
  const parsed = errorBodySchema.safeParse(data);
  if (!parsed.success) return null;
  const errors = parsed.data.errors;
  const located = locatedMessage(errors);
  if (located !== null) return located;
  const detail = detailMessage(parsed.data.detail);
  if (detail !== null) return detail;
  const written = writtenMessage(errors);
  if (written !== null) return written;
  const title = parsed.data.title;
  return typeof title === "string" ? nonEmpty(title) : null;
}

async function fetchJsonRaw(path: string, args?: RequestArgs): Promise<unknown> {
  const method = args?.method ?? "GET";
  const url = buildUrl(path, args?.query);

  const hasBody = args != null && "body" in args && args.body !== undefined;
  const headers: Record<string, string> = {
    ...getAuthHeaders({
      accept: "application/json",
      ...(hasBody ? { contentType: "application/json" } : {}),
    }),
    ...(args?.headers ?? {}),
  };

  const fetchOpts: RequestInit = {
    method,
    headers,
    credentials: "include",
  };
  if (hasBody) {
    const body = args.body;
    fetchOpts.body = JSON.stringify(body ?? null);
  }
  if (args?.signal != null) fetchOpts.signal = args.signal;
  const resp = await fetch(url, fetchOpts);

  const data = await parseResponseBody(resp);

  if (!resp.ok) {
    const msg = extractErrorMessage(data) ?? `HTTP ${resp.status} ${resp.statusText}`;
    throw new APIError(msg, {
      status: resp.status,
      statusText: resp.statusText,
      url,
      data,
    });
  }

  return data;
}

/**
 * Fetch JSON from the API and validate the response against a Zod schema.
 *
 * Every JSON API call goes through this function — there is no unvalidated
 * path. On validation failure a `SchemaValidationError` is thrown.
 */
export async function requestJson<T>(
  schema: z.ZodType<T>,
  path: string,
  args?: RequestArgs,
): Promise<T> {
  const raw = await fetchJsonRaw(path, args);
  const result = schema.safeParse(raw);
  if (!result.success) {
    const url = buildUrl(path, args?.query);
    const issues = result.error.issues;
    if (process.env.NODE_ENV === "development") {
      console.error(`[SchemaValidation] ${path} failed:`, issues, "raw:", raw);
      if (typeof window !== "undefined") {
        try {
          const stored = localStorage.getItem("__schema_errors");
          const log = JSON.parse(stored ?? "[]") as unknown[];
          log.push({ path, issues, raw, ts: Date.now() });
          localStorage.setItem("__schema_errors", JSON.stringify(log.slice(-10)));
        } catch {
          // ignore
        }
      }
    }
    throw new SchemaValidationError(url, issues);
  }
  return result.data;
}

/**
 * Fire-and-forget API call for DELETE / void endpoints.
 *
 * Throws `APIError` on non-2xx responses but does not parse or validate
 * the response body.
 */
export async function requestVoid(path: string, args?: RequestArgs): Promise<void> {
  const method = args?.method ?? "GET";
  const url = buildUrl(path, args?.query);

  const hasBody = args != null && "body" in args && args.body !== undefined;
  const headers: Record<string, string> = {
    ...getAuthHeaders({
      accept: "application/json",
      ...(hasBody ? { contentType: "application/json" } : {}),
    }),
    ...(args?.headers ?? {}),
  };

  const fetchOpts: RequestInit = {
    method,
    headers,
    credentials: "include",
  };
  if (hasBody) fetchOpts.body = JSON.stringify(args.body ?? null);
  if (args?.signal != null) fetchOpts.signal = args.signal;

  const resp = await fetch(url, fetchOpts);

  if (!resp.ok) {
    const data = await parseResponseBody(resp);
    const msg = extractErrorMessage(data) ?? `HTTP ${resp.status} ${resp.statusText}`;
    throw new APIError(msg, {
      status: resp.status,
      statusText: resp.statusText,
      url,
      data,
    });
  }
}
