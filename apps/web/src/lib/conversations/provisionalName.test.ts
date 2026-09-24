import type { UIMessage } from "ai";
import { describe, expect, it } from "vitest";

import { DEFAULT_STREAM_NAME } from "@pathfinder/shared";

import { firstUserMessageText, provisionalName } from "./provisionalName";

import parity from "../../../../../packages/spec/provisional_name_parity.json";

describe("provisionalName", () => {
  it("keeps the conversation name when it has one", () => {
    expect(provisionalName("Kinases in the blood stage", "find kinases")).toBe(
      "Kinases in the blood stage",
    );
  });

  it("shows the first message cut on a word boundary when the name is blank", () => {
    const message =
      "  Find genes upregulated in the Anopheles midgut 24 hours after a blood meal versus sugar fed  ";
    expect(provisionalName("", message)).toBe(
      "Find genes upregulated in the Anopheles midgut 24 hours...",
    );
    expect(provisionalName("   ", "find kinases\n in P. falciparum")).toBe(
      "find kinases in P. falciparum",
    );
  });

  it.each(parity.cases)("names $name as the api does", ({ prompt, expected }) => {
    expect(provisionalName("", prompt)).toBe(expected);
  });

  it("falls back to the default name when there is no message", () => {
    expect(provisionalName("", null)).toBe(DEFAULT_STREAM_NAME);
    expect(provisionalName("", "   ")).toBe(DEFAULT_STREAM_NAME);
  });
});

describe("firstUserMessageText", () => {
  it("reads the text parts of the first user message", () => {
    const messages: UIMessage[] = [
      { id: "a1", role: "assistant", parts: [{ type: "text", text: "hello" }] },
      {
        id: "u1",
        role: "user",
        parts: [
          { type: "text", text: "find kinases" },
          { type: "text", text: "in P. falciparum" },
        ],
      },
      { id: "u2", role: "user", parts: [{ type: "text", text: "and later" }] },
    ];
    expect(firstUserMessageText(messages)).toBe("find kinases in P. falciparum");
  });

  it("is null when no user message carries text", () => {
    expect([
      firstUserMessageText([]),
      firstUserMessageText([
        { id: "u1", role: "user", parts: [{ type: "text", text: "  " }] },
      ]),
    ]).toEqual([null, null]);
  });
});
