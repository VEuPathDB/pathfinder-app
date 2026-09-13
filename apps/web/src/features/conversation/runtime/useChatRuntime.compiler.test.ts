import { describe, expect, it } from "vitest";
import { parseSync, transformSync, traverse } from "@babel/core";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const HOOK_FILE = resolve(
  process.cwd(),
  "src/features/conversation/runtime/useChatRuntime.ts",
);

const CURSOR_STORE = "conversationCursors";

/** Compile one source the way `next build` does, with the React Compiler on. */
function compile(source: string, filename: string): string {
  const result = transformSync(source, {
    filename,
    babelrc: false,
    configFile: false,
    presets: [["@babel/preset-typescript", { isTSX: false, allExtensions: true }]],
    plugins: [["babel-plugin-react-compiler", { target: "19" }]],
  });
  const code = result?.code ?? "";
  if (!code.includes("react/compiler-runtime")) {
    throw new Error(`the React Compiler did not memoize ${filename}`);
  }
  return code;
}

interface CursorRead {
  member: string;
  cached: boolean;
}

/**
 * The cursor reads the compiled hook makes while it renders, and whether the
 * compiler put each one behind its cache. A read inside a nested function runs
 * when React calls that function, so it is not a render read.
 */
function renderCursorReads(code: string, hook: string): CursorRead[] {
  const reads: CursorRead[] = [];
  const ast = parseSync(code, { babelrc: false, configFile: false });
  if (ast === null) throw new Error("the compiled hook did not parse");
  traverse(ast, {
    MemberExpression(path) {
      const { object, property } = path.node;
      if (object.type !== "Identifier" || object.name !== CURSOR_STORE) return;
      if (property.type !== "Identifier") return;
      if (path.parent.type !== "CallExpression") return;
      const owner = path.getFunctionParent();
      const named = owner?.node.type === "FunctionDeclaration" ? owner.node.id : null;
      if (named?.name !== hook) return;
      reads.push({
        member: property.name,
        cached: path.findParent((parent) => parent.isIfStatement()) !== null,
      });
    },
  });
  return reads;
}

/** A hook that reads the cursor store while it renders, which is the hazard. */
const RENDER_READ_HOOK = `
import { useQuery } from "@tanstack/react-query";
import { conversationCursors } from "../api/assistantClient";

export function useProbe({ conversationId }: { conversationId: string }) {
  const delivered = conversationCursors.read(conversationId);
  useQuery({
    queryKey: ["conversations", conversationId, "reattach", delivered],
    queryFn: () => delivered,
  });
  return delivered;
}
`;

describe("useChatRuntime under the React Compiler", () => {
  it("reports a render-phase cursor read as one the compiler caches", () => {
    const code = compile(RENDER_READ_HOOK, "useProbe.ts");

    expect(renderCursorReads(code, "useProbe")).toEqual([
      { member: "read", cached: true },
    ]);
  });

  it("reads the thread's open message on every render, and its cursor from state", () => {
    const code = compile(readFileSync(HOOK_FILE, "utf8"), HOOK_FILE);

    const reads = renderCursorReads(code, "useChatRuntime");
    expect(reads).toEqual([{ member: "readOpenMessage", cached: false }]);
  });
});
