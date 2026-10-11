import { existsSync, readdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const stylesDir = dirname(fileURLToPath(import.meta.url));
const globals = readFileSync(join(stylesDir, "globals.css"), "utf8");
const require = createRequire(join(process.cwd(), "package.json"));

describe("the math a response renders", () => {
  it("is styled by the KaTeX stylesheet, which hides its MathML copy", () => {
    expect(globals.split("\n")).toContain('@import "katex/dist/katex.min.css";');
    const stylesheet = readFileSync(
      require.resolve("katex/dist/katex.min.css"),
      "utf8",
    );
    expect(stylesheet).toMatch(
      /\.katex \.katex-mathml\{[^}]*clip-path:inset\(50%\)[^}]*position:absolute/,
    );
  });

  it("has its plugin's classes scanned by Tailwind", () => {
    const source = /^@source "([^"]*@streamdown\/math\/dist)\/\*\.js";$/m.exec(globals);
    if (source?.[1] === undefined) throw new Error("no @source names the math plugin");
    const dist = resolve(stylesDir, source[1]);
    expect(existsSync(dist)).toBe(true);
    expect(readdirSync(dist)).toContain("index.js");
  });
});
