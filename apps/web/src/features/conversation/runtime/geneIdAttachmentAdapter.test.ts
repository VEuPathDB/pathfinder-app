/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";

import { GeneIdAttachmentAdapter } from "./geneIdAttachmentAdapter";

function pending(file: File) {
  return {
    id: file.name,
    type: "document" as const,
    name: file.name,
    contentType: file.type,
    file,
    status: { type: "requires-action" as const, reason: "composer-send" as const },
  };
}

describe("GeneIdAttachmentAdapter", () => {
  const adapter = new GeneIdAttachmentAdapter();

  it("accepts csv/tsv/txt", () => {
    expect(adapter.accept).toContain(".csv");
    expect(adapter.accept).toContain(".tsv");
    expect(adapter.accept).toContain(".txt");
  });

  it("add() marks the file pending until composer send", async () => {
    const file = new File(["PF3D7_0100100\n"], "c.csv", { type: "text/csv" });
    const result = await adapter.add({ file });
    expect(result.name).toBe("c.csv");
    expect(result.status).toEqual({
      type: "requires-action",
      reason: "composer-send",
    });
  });

  it("send() emits a normalized gene-ids block (first column, no header, deduped)", async () => {
    const file = new File(
      [
        "geneId,product\nPF3D7_0100100,PfEMP1\nPF3D7_0200200,HSP90\nPF3D7_0100100,dup\n",
      ],
      "controls.csv",
      { type: "text/csv" },
    );
    const complete = await adapter.send(pending(file));
    expect(complete.status).toEqual({ type: "complete" });
    const text = complete.content[0];
    expect(text?.type).toBe("text");
    const body = text?.type === "text" ? text.text : "";
    // No pseudo-XML tag (it trips the injection scanner) - plain framing.
    expect(body).not.toContain("<");
    expect(body).toContain("Attached gene-ID list from controls.csv");
    expect(body).toContain("PF3D7_0100100");
    expect(body).toContain("PF3D7_0200200");
    // header + description column + duplicate are excluded
    expect(body).not.toContain("PfEMP1");
    expect(body).not.toContain("geneId");
  });

  it("send() falls back to raw content when nothing parses as gene IDs", async () => {
    const file = new File([""], "empty.csv", { type: "text/csv" });
    const complete = await adapter.send(pending(file));
    const text = complete.content[0];
    const body = text?.type === "text" ? text.text : "";
    expect(body).toContain("no recognizable gene IDs");
    expect(body).toContain("empty.csv");
  });
});
