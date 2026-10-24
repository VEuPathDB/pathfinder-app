import { describe, expect, it } from "vitest";
import {
  auditFindingUrl,
  auditRunUrl,
  auditsUrl,
  chatRoot,
  chatUrl,
  conversationIdFromPath,
  edaTabUrl,
  helpUrl,
  strategyCanvasUrl,
  strategyStepUrl,
  yourDataUrl,
} from "./routes";

describe("route builders", () => {
  it("name no site, since the website that frames PathFinder decides it", () => {
    expect(chatRoot()).toBe("/conversation");
    expect(chatUrl("c1")).toBe("/conversation/c1");
  });

  it("reads the conversation id out of a path, past a query or a hash", () => {
    expect(conversationIdFromPath("/conversation/c1")).toBe("c1");
    expect(conversationIdFromPath("/conversation/c1/strategy")).toBe("c1");
    expect(conversationIdFromPath("/conversation/c1?x=1")).toBe("c1");
    expect(conversationIdFromPath("/conversation")).toBeNull();
    expect(conversationIdFromPath("/conversation?assistant=helper")).toBeNull();
  });

  it("builds the conversation eda path", () => {
    expect(edaTabUrl("conv-1")).toBe("/conversation/conv-1/eda");
  });

  it("builds the strategy canvas path", () => {
    expect(strategyCanvasUrl("conv-1")).toBe("/conversation/conv-1/strategy");
  });

  it("builds a step deep link under the canvas path", () => {
    expect(strategyStepUrl("conv-1", "step_1")).toBe(
      "/conversation/conv-1/strategy/step/step_1",
    );
  });

  it("builds the site-less help and data statement paths", () => {
    expect(helpUrl()).toBe("/help");
    expect(yourDataUrl()).toBe("/help/your-data");
    expect(yourDataUrl("declined")).toBe("/help/your-data#declined");
  });

  it("builds the audit addresses with the filters they carry", () => {
    expect(auditsUrl()).toBe("/audits");
    expect(auditRunUrl("0a1b")).toBe("/audits/0a1b");
    expect(auditRunUrl("0a1b", "?origin=target")).toBe("/audits/0a1b?origin=target");
    expect(auditFindingUrl("0a1b", 7)).toBe("/audits/0a1b/findings/7");
    expect(auditFindingUrl("0a1b", 7, "?check=gene_length")).toBe(
      "/audits/0a1b/findings/7?check=gene_length",
    );
  });
});
