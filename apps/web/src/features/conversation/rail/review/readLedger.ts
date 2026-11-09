import type { BuildSection } from "@pathfinder/shared/generated/types/BuildSection";
import type { ConstraintSection } from "@pathfinder/shared/generated/types/ConstraintSection";
import type { FrameSection } from "@pathfinder/shared/generated/types/FrameSection";
import type { UserIntent } from "@pathfinder/shared/generated/types/UserIntent";
import type { VerificationSection } from "@pathfinder/shared/generated/types/VerificationSection";
import { buildSectionSchema } from "@pathfinder/shared/generated/zod/buildSectionSchema";
import { constraintSectionSchema } from "@pathfinder/shared/generated/zod/constraintSectionSchema";
import { frameSectionSchema } from "@pathfinder/shared/generated/zod/frameSectionSchema";
import { userIntentSchema } from "@pathfinder/shared/generated/zod/userIntentSchema";
import { verificationSectionSchema } from "@pathfinder/shared/generated/zod/verificationSectionSchema";
import type { UIMessage } from "ai";
import { z } from "zod";

export interface LedgerView {
  userIntent: UserIntent | null;
  frame: FrameSection | null;
  build: BuildSection | null;
  verification: VerificationSection | null;
  constraints: ConstraintSection | null;
}

type ListPath = readonly string[];

const RECORD = z.record(z.string(), z.unknown());
const LIST = z.array(z.unknown());
const MAX_ROUNDS = 8;

const INTENT_LISTS: readonly ListPath[] = [["explicitConstraints"]];
const VERIFICATION_LISTS: readonly ListPath[] = [
  ["caveats"],
  ["digest", "caveats"],
  ["digest", "gaps"],
];
const CONSTRAINT_LISTS: readonly ListPath[] = [["grounded"]];
const BUILD_LISTS: readonly ListPath[] = [["nodeResults"]];

interface Drop {
  list: ListPath;
  index: number;
}

function dropFor(
  path: readonly PropertyKey[],
  lists: readonly ListPath[],
): Drop | null {
  for (const list of lists) {
    const index = path[list.length];
    if (typeof index !== "number") continue;
    if (list.every((key, i) => path[i] === key)) return { list, index };
  }
  return null;
}

function isNullBranch(issues: readonly z.core.$ZodIssue[]): boolean {
  return issues.every(
    (issue) => issue.code === "invalid_type" && issue.expected === "null",
  );
}

function leafIssues(issue: z.core.$ZodIssue): { path: readonly PropertyKey[] }[] {
  if (issue.code !== "invalid_union") return [issue];
  const branches = issue.errors.filter((branch) => !isNullBranch(branch));
  const [only, ...others] = branches;
  if (only === undefined || others.length > 0) return [issue];
  return only.flatMap((inner) =>
    leafIssues(inner).map((leaf) => ({ path: [...issue.path, ...leaf.path] })),
  );
}

function withoutEntries(
  value: unknown,
  path: ListPath,
  indices: ReadonlySet<number>,
): unknown {
  const record = RECORD.safeParse(value);
  const [key, ...rest] = path;
  if (!record.success || key === undefined) return value;
  const child = record.data[key];
  if (rest.length > 0) {
    return { ...record.data, [key]: withoutEntries(child, rest, indices) };
  }
  const list = LIST.safeParse(child);
  if (!list.success) return value;
  return { ...record.data, [key]: list.data.filter((_, i) => !indices.has(i)) };
}

function readSection<T>(
  schema: z.ZodType<T>,
  raw: unknown,
  lists: readonly ListPath[] = [],
): T | null {
  let current = raw;
  for (let round = 0; round < MAX_ROUNDS; round++) {
    const parsed = schema.safeParse(current);
    if (parsed.success) return parsed.data;
    const drops = parsed.error.issues
      .flatMap(leafIssues)
      .map((issue) => dropFor(issue.path, lists));
    if (drops.some((drop) => drop === null)) return null;
    for (const list of lists) {
      const indices = new Set(
        drops.filter((drop) => drop?.list === list).map((drop) => drop?.index ?? -1),
      );
      if (indices.size > 0) current = withoutEntries(current, list, indices);
    }
  }
  return null;
}

export function readLedger(raw: unknown): LedgerView | null {
  const ledger = RECORD.safeParse(raw);
  if (!ledger.success) return null;
  const sections = ledger.data;
  return {
    userIntent: readSection(userIntentSchema, sections["userIntent"], INTENT_LISTS),
    frame: readSection(frameSectionSchema, sections["frame"]),
    build: readSection(buildSectionSchema, sections["build"], BUILD_LISTS),
    verification: readSection(
      verificationSectionSchema,
      sections["verification"],
      VERIFICATION_LISTS,
    ),
    constraints: readSection(
      constraintSectionSchema,
      sections["constraints"],
      CONSTRAINT_LISTS,
    ),
  };
}

export function latestLedgerView(messages: readonly UIMessage[]): LedgerView | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const parts = messages[i]?.parts ?? [];
    for (let j = parts.length - 1; j >= 0; j--) {
      const part = parts[j];
      if (part?.type !== "data-ledger-update" || !("data" in part)) continue;
      const view = readLedger(part.data);
      if (view !== null) return view;
    }
  }
  return null;
}
