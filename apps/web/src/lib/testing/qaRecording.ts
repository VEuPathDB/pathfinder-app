import { existsSync, readFileSync } from "node:fs";
import { test } from "vitest";

export const NEEDS_QA_RECORDING =
  "needs a QA recording: re-record once QA access exists";

export function qaRecording(url: URL): unknown {
  if (existsSync(url)) return JSON.parse(readFileSync(url, "utf8"));
  test.skip(NEEDS_QA_RECORDING, () => {});
  return null;
}
