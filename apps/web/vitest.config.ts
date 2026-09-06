import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

const srcDir = fileURLToPath(new URL("./src", import.meta.url));
const sharedDir = fileURLToPath(
  new URL("../../packages/shared-ts/src", import.meta.url),
);
const webNodeModules = fileURLToPath(new URL("./node_modules", import.meta.url));

export default defineConfig({
  resolve: {
    alias: [
      { find: "@/", replacement: `${srcDir}/` },
      {
        find: /^@pathfinder\/shared\/generated\/(.*)$/,
        replacement: `${sharedDir}/generated/$1`,
      },
      { find: "@pathfinder/shared", replacement: sharedDir },
      {
        find: "@tanstack/react-query",
        replacement: `${webNodeModules}/@tanstack/react-query`,
      },
      { find: /^react$/, replacement: `${webNodeModules}/react` },
      { find: /^react-dom$/, replacement: `${webNodeModules}/react-dom` },
    ],
  },
  test: {
    setupFiles: ["./vitest.setup.ts", "./vitest.msw-setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      // Unit coverage focuses on app "logic layers"; UI is covered by Playwright E2E.
      include: [
        "src/lib/**/*.{ts,tsx}",
        // Conversation logic modules (unit-tested); its React renderers,
        // transport and hooks are covered by Playwright E2E.
        "src/features/conversation/content/parts/consultData.ts",
        "src/features/conversation/content/statusClock.ts",
        "src/features/conversation/rail/{consultActions,normalizeLedger,railActivity}.ts",
        "src/features/conversation/runtime/{buildRequestBody,geneIdAttachmentAdapter}.ts",
        "src/features/conversation/slash/{parser,registryUtils}.ts",
        // ReactFlow graph interaction logic (unit-tested).
        "src/features/strategy/graph/utils/**/*.{ts,tsx}",
        "src/state/**/*.{ts,tsx}",
        // Pure strategy graph logic (unit-tested).
        "src/features/strategy/graph/{kind,serialize,validate,deserialize}.ts",
      ],
      exclude: [
        // UI rendering is primarily covered by Playwright E2E.
        "src/app/**",
        "src/**/components/**",
        "src/features/**/graph/components/**",
        "src/features/**/graph/hooks/**",
        "src/features/**/editor/**",
        "src/features/sites/**",
        "**/*.d.ts",
        "**/*.config.*",
        "**/e2e/**",
        "**/node_modules/**",
        "**/.next/**",
      ],
      thresholds: {
        statements: 80,
        lines: 80,
        branches: 70,
        functions: 60,
      },
    },
  },
});
