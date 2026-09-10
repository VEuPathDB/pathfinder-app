import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import { describe, expect, it } from "vitest";

const SRC = fileURLToPath(new URL(".", import.meta.url));

const SCANNED = ["features", "app", "lib/components", "lib/models", "lib/utils"];

/** The words that name PathFinder's internals rather than the researcher's work. */
const INTERNAL = /\b(EDA|WDK|FRAME|BUILD|VERIFY|Frame|Ledger|Lead|sub-agent)\b/;

/**
 * The one exception: a stream part kind, with or without the `data-` prefix
 * the wire adds. Every other internal name is lowercase where it is allowed
 * (testids, routes, query keys, field names), so the pattern above passes it.
 */
const PART_KIND = /^(data-)?(sub-agent|eda)[a-z0-9.-]*$/;

type Hit = { where: string; text: string };

function sourceFiles(): string[] {
  const found: string[] = [];
  const walk = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(path);
        continue;
      }
      if (!/\.tsx?$/.test(entry.name) || /\.(test|spec)\.tsx?$/.test(entry.name)) {
        continue;
      }
      found.push(path);
    }
  };
  SCANNED.forEach((dir) => walk(join(SRC, dir)));
  return found;
}

function texts(path: string): { node: ts.Node; text: string; line: number }[] {
  const body = readFileSync(path, "utf8");
  const tree = ts.createSourceFile(
    path,
    body,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const found: { node: ts.Node; text: string; line: number }[] = [];
  const visit = (node: ts.Node): void => {
    const raw =
      ts.isStringLiteral(node) ||
      ts.isNoSubstitutionTemplateLiteral(node) ||
      ts.isTemplateHead(node) ||
      ts.isTemplateMiddle(node) ||
      ts.isTemplateTail(node) ||
      ts.isJsxText(node)
        ? node.text
        : null;
    if (raw !== null) {
      const { line } = tree.getLineAndCharacterOfPosition(node.getStart(tree));
      found.push({ node, text: raw.trim(), line: line + 1 });
    }
    ts.forEachChild(node, visit);
  };
  visit(tree);
  return found;
}

function scan(): { scanned: number; violations: Hit[]; excused: Hit[] } {
  const violations: Hit[] = [];
  const excused: Hit[] = [];
  const paths = sourceFiles();
  for (const path of paths) {
    for (const { text, line } of texts(path)) {
      if (!INTERNAL.test(text)) continue;
      const hit = { where: `${relative(SRC, path)}:${String(line)}`, text };
      (PART_KIND.test(text) ? excused : violations).push(hit);
    }
  }
  return { scanned: paths.length, violations, excused };
}

describe("the copy a researcher reads", () => {
  // One parse of every source file feeds all three assertions.
  const result = scan();

  it("scans every non-test source under the copy-bearing trees", () => {
    expect(result.scanned).toBeGreaterThan(200);
  });

  it("names no internal word in any string literal or JSX text", () => {
    expect(result.violations.map((v) => `${v.where} ${v.text}`)).toEqual([]);
  });

  it("excuses part kinds only, and the exception is still used", () => {
    expect(new Set(result.excused.map((e) => e.text))).toEqual(
      new Set(["data-sub-agent-call", "data-sub-agent-step"]),
    );
  });
});
