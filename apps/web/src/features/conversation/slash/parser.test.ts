import { describe, it, expect } from "vitest";

import { fuzzyPrefix, matchCommandName, parseSlashInput } from "./parser";

describe("parseSlashInput", () => {
  it("returns null unless the slash opens the input", () => {
    expect(parseSlashInput("hello")).toEqual(null);
    expect(parseSlashInput("say /export")).toEqual(null);
    expect(parseSlashInput("")).toEqual(null);
  });

  it("parses bare command", () => {
    expect(parseSlashInput("/export")).toEqual({ token: "export", rest: "" });
  });

  it("parses command with args", () => {
    expect(parseSlashInput("/export strategy json")).toEqual({
      token: "export",
      rest: "strategy json",
    });
  });

  it("parses empty slash (for popover trigger)", () => {
    expect(parseSlashInput("/")).toEqual({ token: "", rest: "" });
  });
});

describe("matchCommandName", () => {
  it("matches exact name", () => {
    expect(matchCommandName("export", { name: "export" })).toBe(true);
  });
  it("is case insensitive", () => {
    expect(matchCommandName("Export", { name: "export" })).toBe(true);
  });
  it("matches alias", () => {
    expect(matchCommandName("dl", { name: "export", aliases: ["dl"] })).toBe(true);
  });
  it("rejects non-match", () => {
    expect(matchCommandName("foo", { name: "export" })).toBe(false);
  });
});

describe("fuzzyPrefix", () => {
  it("matches prefix of name", () => {
    expect(fuzzyPrefix("exp", { name: "export" })).toBe(true);
  });
  it("matches prefix of alias", () => {
    expect(fuzzyPrefix("d", { name: "export", aliases: ["dl"] })).toBe(true);
  });
  it("empty token matches everything", () => {
    expect(fuzzyPrefix("", { name: "export" })).toBe(true);
  });
  it("returns false for non-prefix", () => {
    expect(fuzzyPrefix("xx", { name: "export" })).toBe(false);
  });
});
