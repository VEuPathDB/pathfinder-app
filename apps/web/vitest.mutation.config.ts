import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

/**
 * Vitest config for Stryker mutation runs.
 *
 * Stryker dry-runs the ENTIRE suite before mutating anything, so pulling in
 * component tests both slows every mutant and fails on workspace imports the
 * sandbox cannot resolve. Mutation scope (stryker.config.json) is the pure
 * state layer, so the test scope is narrowed to match.
 *
 * Declared standalone rather than via ``mergeConfig``: that CONCATENATES
 * array options, so a narrower ``include`` would be appended to the base
 * glob instead of replacing it, and the whole suite would run anyway.
 */
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
    include: ["src/state/strategy/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**"],
  },
});
