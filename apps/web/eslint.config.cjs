const { defineConfig } = require("eslint/config");
const nextConfig = require("eslint-config-next/core-web-vitals");

const tsBlock = nextConfig.find((b) => b.name === "next/typescript");
const tsPlugin = tsBlock?.plugins?.["@typescript-eslint"];

module.exports = defineConfig([
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "playwright-report/**",
      "test-results/**",
      "coverage/**",
      // Stryker keeps one sandbox copy of the tree per mutation run, so a
      // whole-directory lint would type-check the project several times over.
      ".stryker-tmp/**",
      "reports/**",
      // Vendored shadcn / AI Elements primitives — copied via shadcn CLI.
      // Treat as third-party; lint rules apply to PathFinder code only.
      "src/components/ui/**",
      "src/components/ai-elements/**",
    ],
  },
  ...nextConfig,
  // TypeScript type-aware rules (the big guns).
  ...(tsPlugin
    ? [
        {
          files: ["**/*.ts", "**/*.tsx"],
          plugins: { "@typescript-eslint": tsPlugin },
          languageOptions: {
            parserOptions: {
              projectService: true,
              tsconfigRootDir: __dirname,
            },
          },
          rules: {
            // --- Existing ---
            "@typescript-eslint/no-explicit-any": "error",
            "@typescript-eslint/no-require-imports": "error",

            // --- Async bugs (catch REAL production crashes) ---
            "@typescript-eslint/no-floating-promises": "error",
            "@typescript-eslint/no-misused-promises": "error",
            "@typescript-eslint/await-thenable": "error",

            // --- Type safety (no unsafe escape hatches) ---
            "@typescript-eslint/no-unnecessary-type-assertion": "error",
            "@typescript-eslint/no-unsafe-assignment": "error",
            "@typescript-eslint/no-unsafe-call": "error",
            "@typescript-eslint/no-unsafe-member-access": "error",
            "@typescript-eslint/no-unsafe-return": "error",
            "@typescript-eslint/no-unsafe-argument": "error",

            // --- Code quality ---
            "@typescript-eslint/no-unused-vars": [
              "error",
              { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
            ],
            "@typescript-eslint/prefer-nullish-coalescing": "error",
            "@typescript-eslint/prefer-optional-chain": "error",
            "@typescript-eslint/strict-boolean-expressions": "error",
            "@typescript-eslint/switch-exhaustiveness-check": "error",
            "@typescript-eslint/no-unnecessary-condition": "error",
            "@typescript-eslint/consistent-type-imports": [
              "error",
              { prefer: "type-imports", fixStyle: "inline-type-imports" },
            ],

            // --- React ---
            "react-hooks/exhaustive-deps": "error",
            "no-restricted-imports": [
              "error",
              {
                paths: [
                  {
                    name: "react",
                    importNames: ["useEffect"],
                    message:
                      "useEffect is banned. Use TanStack Query, usehooks-ts, Zustand subscribe, or render-time patterns instead. See https://react.dev/learn/you-might-not-need-an-effect",
                  },
                  {
                    name: "react",
                    importNames: ["useMemo", "useCallback"],
                    message:
                      "useMemo/useCallback are redundant — React Compiler (babel-plugin-react-compiler) handles memoization automatically with better data-flow analysis than manual dependency arrays.",
                  },
                ],
              },
            ],

            // --- No stray console.log ---
            "no-console": ["error", { allow: ["warn", "error"] }],

            // --- File size limit ---
            "max-lines": [
              "error",
              { max: 300, skipBlankLines: true, skipComments: true },
            ],
          },
        },
        // Relax rules for test files
        {
          files: ["**/*.test.{ts,tsx}", "e2e/**/*.spec.ts"],
          plugins: { "@typescript-eslint": tsPlugin },
          rules: {
            "@typescript-eslint/no-explicit-any": "off",
            "@typescript-eslint/no-unsafe-assignment": "off",
            "@typescript-eslint/no-unsafe-call": "off",
            "@typescript-eslint/no-unsafe-member-access": "off",
            "@typescript-eslint/no-unsafe-return": "off",
            "@typescript-eslint/no-unsafe-argument": "off",
            "@typescript-eslint/no-floating-promises": "off",
            "@typescript-eslint/strict-boolean-expressions": "off",
            "no-console": "off",
            "max-lines": "off",
          },
        },
        // Playwright fixtures use a callback named "use", not React hooks.
        {
          files: ["e2e/**/*.ts"],
          rules: { "react-hooks/rules-of-hooks": "off" },
        },
        {
          files: ["src/features/workbench/analysis/components/ResultsTable/**"],
          rules: { "react-hooks/incompatible-library": "off" },
        },
        {
          files: ["**/*.cjs", "next.config.js"],
          plugins: { "@typescript-eslint": tsPlugin },
          rules: { "@typescript-eslint/no-require-imports": "off" },
        },
      ]
    : []),
]);
