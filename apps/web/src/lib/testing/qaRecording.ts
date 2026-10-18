import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "vitest";

export const NEEDS_QA_RECORDING =
  "needs a QA recording: re-record once QA access exists";

export function qaRecording(moduleUrl: string, relativePath: string): unknown {
  const file = fileURLToPath(new URL(relativePath, moduleUrl));
  if (existsSync(file)) return JSON.parse(readFileSync(file, "utf8"));
  test.skip(NEEDS_QA_RECORDING, () => {});
  return null;
}
