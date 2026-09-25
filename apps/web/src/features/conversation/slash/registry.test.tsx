/**
 * @vitest-environment jsdom
 */
import { QueryClient } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { chatRoot } from "@/lib/routes";

import { SlashPopover } from "./SlashPopover";
import { matchCommandName } from "./parser";
import { commands } from "./registry";
import type { Command, CommandContext } from "./types";

function ctx(overrides: Partial<CommandContext> = {}): CommandContext {
  return {
    conversationId: "c1",
    siteId: "plasmodb",
    stepCount: 0,
    conversationExists: true,
    queryClient: new QueryClient(),
    ...overrides,
  };
}

function command(name: string): Command {
  const found = commands.find((c) => matchCommandName(name, c));
  if (found === undefined) throw new Error(`no /${name} in the registry`);
  return found;
}

async function runDeterministic(name: string, context: CommandContext) {
  const found = command(name);
  if (found.kind !== "deterministic") throw new Error(`/${name} is not deterministic`);
  return found.run({}, context);
}

describe("the slash registry", () => {
  it("names each command and alias once", () => {
    const names = commands.flatMap((c) => [c.name, ...(c.aliases ?? [])]);
    expect(new Set(names).size).toBe(names.length);
  });

  it("/help reopens the command list", async () => {
    expect(await runDeterministic("help", ctx())).toEqual({
      kind: "prefill",
      text: "/",
    });
  });

  it("/? is /help", () => {
    expect(command("?").name).toBe("help");
  });

  it("/new opens a new chat on the current site", async () => {
    expect(await runDeterministic("new", ctx({ siteId: "toxodb" }))).toEqual({
      kind: "navigate",
      href: chatRoot("toxodb"),
    });
  });

  it.each(["clear", "analyze", "diagnose", "explain"])(
    "/%s is refused on a chat with no strategy",
    (name) => {
      expect(command(name).disabledReason?.(ctx({ stepCount: 0 }))).toBe(
        "This conversation has no strategy yet.",
      );
      expect(command(name).disabledReason?.(ctx({ stepCount: 2 }))).toBe(null);
    },
  );

  it.each([
    ["clear", {}, /^Clear the current strategy by calling clear_strategy/, true],
    ["analyze", {}, /^Analyze my current strategy\./, false],
    ["summarize", {}, /^Summarize this conversation so far/, false],
    [
      "diagnose",
      {},
      /^Diagnose my current strategy\. Call get_live_strategy_state, walk through each step's count/,
      false,
    ],
    ["explain", { stepHint: " the GO step " }, /^Explain what the GO step does/, false],
    ["explain", {}, /^Explain what my last step does/, false],
  ])("/%s inserts its prompt", (name, values, prompt, submits) => {
    const found = command(name);
    if (found.kind !== "llm-prefill") throw new Error(`/${name} is not a prompt`);
    expect(found.prompt(values, ctx())).toMatch(prompt);
    expect(found.autoSubmit === true).toBe(submits);
  });

  it("/export offers only the combinations it can write", () => {
    const [what] = command("export").params;
    expect(what?.kind === "select" ? what.options.map((o) => o.value) : []).toEqual([
      "strategy-json",
      "chat-md",
      "chat-json",
      "gene-set-csv",
      "gene-set-txt",
    ]);
  });

  it("/export refuses the strategy of a chat that has none", async () => {
    const exportCommand = command("export");
    if (exportCommand.kind !== "deterministic") throw new Error("not deterministic");
    expect(await exportCommand.run({ what: "strategy-json" }, ctx())).toEqual({
      kind: "toast",
      type: "error",
      message: "This conversation has no strategy yet.",
    });
  });

  it("/export refuses the transcript of a chat that has not started", async () => {
    const exportCommand = command("export");
    if (exportCommand.kind !== "deterministic") throw new Error("not deterministic");
    expect(
      await exportCommand.run({ what: "chat-md" }, ctx({ conversationExists: false })),
    ).toEqual({
      kind: "toast",
      type: "error",
      message: "This conversation has no messages yet.",
    });
  });
});

describe("/help", () => {
  it("lists every registry command with its description", () => {
    render(
      <SlashPopover
        open
        query=""
        commands={commands}
        activeIdx={0}
        onSelect={() => {}}
        onHover={() => {}}
      />,
    );
    for (const c of commands) {
      expect(screen.getByTestId(`slash-item-${c.name}`)).toHaveTextContent(
        `/${c.name}`,
      );
      expect(screen.getByTestId(`slash-item-${c.name}`)).toHaveTextContent(
        c.description,
      );
    }
    expect(screen.getAllByRole("option")).toHaveLength(commands.length);
  });
});
