import { z } from "zod";

import { APIError, extractErrorMessage } from "./http";
import { AppError } from "@/lib/errors/AppError";

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

type ZodIssue = z.core.$ZodIssue;

/** The issue that reached furthest into the value, through every union option. */
function deepestIssue(
  issue: ZodIssue,
  prefix: readonly PropertyKey[],
): { issue: ZodIssue; path: PropertyKey[] } {
  let best = { issue, path: [...prefix, ...issue.path] };
  if (issue.code !== "invalid_union") return best;
  for (const inner of issue.errors.flat()) {
    const found = deepestIssue(inner, best.path);
    if (found.path.length > best.path.length) best = found;
  }
  return best;
}

/** One sentence that names the field a request body failed on, never the issue list. */
function invalidBodyMessage(err: z.ZodError, fallback: string): string {
  const lead = fallback.replace(/\.$/, "");
  const first = err.issues[0];
  if (first === undefined) return fallback;
  const { issue, path } = deepestIssue(first, []);
  const names = path.filter((part): part is string => typeof part === "string");
  // Inside a parameter map, the parameter's name is the field the user knows.
  const inParameters = names.indexOf("parameters");
  const field =
    inParameters >= 0 && inParameters + 1 < names.length
      ? names[inParameters + 1]
      : names.at(-1);
  if (field === undefined) return fallback;
  const problem =
    issue.code === "too_small" ? "is missing a value" : "has an invalid value";
  return `${lead}: ${field} ${problem}`;
}

export function toUserMessage(err: unknown, fallback = "Request failed."): string {
  if (err == null) return fallback;

  if (err instanceof z.ZodError) return invalidBodyMessage(err, fallback);

  if (err instanceof AppError) {
    const msg = err.message.trim();
    return msg !== "" ? msg : fallback;
  }

  if (err instanceof APIError) {
    const problem = extractErrorMessage(err.data);
    if (problem !== null) return problem;
    const msg = err.message.trim();
    return msg !== "" ? msg : err.statusText !== "" ? err.statusText : fallback;
  }

  // fetch rejects with a TypeError when the network fails, and its message is
  // the browser's, not a sentence written for the user.
  if (err instanceof TypeError) return fallback;

  if (err instanceof Error) {
    // The chat transport rethrows the response body as the message.
    const body = extractErrorMessage(parseJson(err.message));
    if (body !== null) return body;
    const msg = err.message.trim();
    return msg !== "" ? msg : fallback;
  }

  try {
    const msg = String(err).trim();
    return msg !== "" ? msg : fallback;
  } catch {
    return fallback;
  }
}

const wdkAuthRefusalSchema = z.object({
  code: z.union([z.literal("WDK_LOGIN_REQUIRED"), z.literal("WDK_IDENTITY_MISMATCH")]),
  detail: z.string().min(1),
});

/** A refusal about which VEuPathDB account the request acts as. */
type WdkAuthRefusal = z.infer<typeof wdkAuthRefusalSchema>;

/**
 * The server's refusal when a route wants a VEuPathDB login or reports that the
 * token names another account, or null for every other error. The chat
 * transport rethrows the response body as the message of a plain Error, so both
 * shapes are read here.
 */
export function wdkAuthRefusal(err: unknown): WdkAuthRefusal | null {
  if (!(err instanceof Error)) return null;
  if (err instanceof APIError && err.status !== 401) return null;
  const body = err instanceof APIError ? err.data : parseJson(err.message);
  const problem = wdkAuthRefusalSchema.safeParse(body);
  return problem.success ? problem.data : null;
}

const siteUnavailableSchema = z.object({
  code: z.literal("SITE_UNAVAILABLE"),
  detail: z.string().min(1),
});

/** A refusal that says PathFinder cannot reach the request's VEuPathDB site. */
type SiteUnavailableRefusal = z.infer<typeof siteUnavailableSchema>;

/**
 * The server's refusal when the site a request names has no loaded catalog or
 * did not answer, or null for every other error.
 */
export function siteUnavailableRefusal(err: unknown): SiteUnavailableRefusal | null {
  if (!(err instanceof Error)) return null;
  if (err instanceof APIError && err.status !== 503) return null;
  const body = err instanceof APIError ? err.data : parseJson(err.message);
  const problem = siteUnavailableSchema.safeParse(body);
  return problem.success ? problem.data : null;
}

const notOnSiteSchema = z.object({
  code: z.literal("INVALID_STRATEGY"),
  detail: z.string().min(1),
});

/** A refusal that says a step has no WDK step on its site yet. */
type NotOnSiteRefusal = z.infer<typeof notOnSiteSchema>;

/** The server's 409 when a step is not on its site yet, or null for every other error. */
export function notOnSiteRefusal(err: unknown): NotOnSiteRefusal | null {
  if (!(err instanceof APIError) || err.status !== 409) return null;
  const problem = notOnSiteSchema.safeParse(err.data);
  return problem.success ? problem.data : null;
}
