import { describe, expect, it } from "vitest";
import type { ModelCatalogEntry } from "@pathfinder/shared";

import {
  MAX_ATTACHMENT_BYTES,
  acceptFor,
  attachHint,
  attachLabel,
  attachmentKind,
  fileRefusal,
  messageRefusal,
  readerModel,
  notAcceptedSentence,
  readsLabel,
} from "./attachments";

function model(id: string, name: string, reads: boolean): ModelCatalogEntry {
  const [provider = "", modelName = ""] = id.split(":");
  return {
    id,
    name,
    modelName,
    provider: provider as ModelCatalogEntry["provider"],
    enabled: true,
    supportsImages: reads,
    supportsDocuments: reads,
  };
}

const LUNA = model("openai:gpt-5.6-luna", "GPT-5.6 Luna", true);
const FLASH = model("google:gemini-3.6-flash", "Gemini 3.6 Flash", true);
const SONNET = model("anthropic:claude-sonnet-5", "Claude Sonnet 5", false);
const CATALOG = [LUNA, FLASH, SONNET];
const MIB = 1024 * 1024;

function file(
  name: string,
  type: string,
  size = 100,
): { name: string; type: string; size: number } {
  return { name, type, size };
}

describe("attachmentKind", () => {
  it.each([
    ["ids.csv", "text/csv", "gene-ids"],
    ["ids.tsv", "", "gene-ids"],
    ["ids.txt", "text/plain", "gene-ids"],
    ["table.png", "image/png", "image"],
    ["photo.jpeg", "image/jpeg", "image"],
    ["scan.webp", "image/webp", "image"],
    ["anim.gif", "image/gif", "image"],
    ["paper.pdf", "application/pdf", "pdf"],
    ["page.html", "text/html", null],
    ["vector.svg", "image/svg+xml", null],
  ])("%s (%s) is %s", (name, type, kind) => {
    expect(attachmentKind(file(name, type))).toBe(kind);
  });
});

describe("acceptFor", () => {
  it("offers images and PDFs only to a model that reads them", () => {
    expect(acceptFor(LUNA)).toBe(
      ".csv,.tsv,.txt,text/csv,text/tab-separated-values,text/plain," +
        "image/png,image/jpeg,image/webp,image/gif,application/pdf",
    );
    expect(acceptFor(SONNET)).toBe(
      ".csv,.tsv,.txt,text/csv,text/tab-separated-values,text/plain",
    );
  });
});

describe("fileRefusal", () => {
  it("accepts a file at the per-file cap", () => {
    expect(fileRefusal(file("ids.csv", "text/csv", MAX_ATTACHMENT_BYTES))).toBe(null);
  });

  it("refuses a file over the per-file cap", () => {
    expect(
      fileRefusal(file("big.png", "image/png", MAX_ATTACHMENT_BYTES + 2 * MIB)),
    ).toBe("big.png is 12.0 MB; one attachment can be at most 10 MB.");
  });
});

describe("messageRefusal", () => {
  it("accepts six files within 20 MB", () => {
    expect(messageRefusal(Array.from({ length: 6 }, () => 3 * MIB))).toBe(null);
  });

  it("refuses a seventh file", () => {
    expect(messageRefusal(Array.from({ length: 7 }, () => 10))).toBe(
      "One message can carry at most 6 attachments; this one has 7.",
    );
  });

  it("refuses a message over 20 MB", () => {
    expect(messageRefusal([8 * MIB, 8 * MIB, 8 * MIB])).toBe(
      "These attachments come to 24.0 MB; one message can carry at most 20 MB.",
    );
  });
});

describe("readerModel", () => {
  const defaults = { lead: SONNET.id, frame: LUNA.id, site_help: FLASH.id };

  it("reads the Lead's model for a PathFinder thread", () => {
    expect(readerModel("pathfinder", {}, defaults, CATALOG)).toBe(SONNET);
    expect(readerModel("pathfinder", { lead: LUNA.id }, defaults, CATALOG)).toBe(LUNA);
  });

  it("reads the one agent's model for a site help thread", () => {
    expect(readerModel("site_help", {}, defaults, CATALOG)).toBe(FLASH);
  });

  it("is unknown while the catalog has not loaded", () => {
    expect(readerModel("pathfinder", {}, defaults, [])).toBe(undefined);
  });
});

describe("attachLabel and attachHint", () => {
  it("name what the reader takes", () => {
    expect(attachLabel(LUNA)).toBe("Attach a gene-ID list, an image or a PDF");
    expect(attachHint(LUNA)).toBe(null);
  });

  it("say why a reader that reads no file is offered gene-ID lists alone", () => {
    expect(attachLabel(SONNET)).toBe("Attach a gene-ID list");
    expect(attachHint(SONNET)).toBe(
      "Claude Sonnet 5 does not read images or PDFs; choose a model that does in Settings.",
    );
  });
});

describe("readsLabel", () => {
  it("names the kinds a model reads", () => {
    expect(readsLabel(LUNA)).toBe("reads images and PDFs");
    expect(readsLabel({ ...LUNA, supportsDocuments: false })).toBe("reads images");
    expect(readsLabel(SONNET)).toBe(null);
  });
});

describe("notAcceptedSentence", () => {
  it("says why a reader takes no image, else which kinds are read", () => {
    expect(notAcceptedSentence(SONNET)).toBe(
      "Claude Sonnet 5 does not read images or PDFs; choose a model that does in Settings.",
    );
    expect(notAcceptedSentence(LUNA)).toBe(
      "PathFinder reads gene-ID lists (.csv, .tsv, .txt), images (PNG, JPEG, WebP, GIF) and PDFs.",
    );
  });
});
