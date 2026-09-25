/**
 * @vitest-environment jsdom
 */
import { deflateSync, inflateSync } from "node:zlib";
import { afterEach, describe, it, expect, vi } from "vitest";
import type { ModelCatalogEntry } from "@pathfinder/shared";

import { ChatAttachmentAdapter } from "./chatAttachmentAdapter";

function model(name: string, reads: boolean): ModelCatalogEntry {
  return {
    id: `openai:${name}`,
    name,
    modelName: name,
    provider: "openai",
    enabled: true,
    supportsImages: reads,
    supportsDocuments: reads,
  };
}

const READER = model("GPT-5.6 Luna", true);
const TEXT_ONLY = model("Claude Sonnet 5", false);

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

const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

const RGBA = 6;

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type: string, data: Uint8Array): Uint8Array {
  const body = new Uint8Array([...new TextEncoder().encode(type), ...data]);
  const out = new Uint8Array(body.length + 8);
  const view = new DataView(out.buffer);
  view.setUint32(0, data.length);
  out.set(body, 4);
  view.setUint32(body.length + 4, crc32(body));
  return out;
}

/** An 8-bit RGBA PNG, every row unfiltered. */
function encodePng(width: number, height: number, rgba: ArrayLike<number>): Uint8Array {
  const header = new Uint8Array(13);
  const view = new DataView(header.buffer);
  view.setUint32(0, width);
  view.setUint32(4, height);
  header.set([8, RGBA, 0, 0, 0], 8);
  const rows = new Uint8Array(height * (width * 4 + 1));
  for (let y = 0; y < height; y++) {
    rows.set(
      Array.from(rgba).slice(y * width * 4, (y + 1) * width * 4),
      y * (width * 4 + 1) + 1,
    );
  }
  return new Uint8Array([
    ...PNG,
    ...chunk("IHDR", header),
    ...chunk("IDAT", deflateSync(rows)),
    ...chunk("IEND", new Uint8Array()),
  ]);
}

interface Pixels {
  width: number;
  height: number;
  rgba: Uint8ClampedArray;
}

/** The pixels of a PNG `encodePng` wrote. */
function decodePng(bytes: Uint8Array): Pixels {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (!PNG.every((byte, index) => bytes[index] === byte)) {
    throw new Error("not a PNG");
  }
  let offset = PNG.length;
  let width = 0;
  let height = 0;
  const idat: number[] = [];
  while (offset < bytes.length) {
    const length = view.getUint32(offset);
    const type = new TextDecoder().decode(bytes.slice(offset + 4, offset + 8));
    const data = bytes.slice(offset + 8, offset + 8 + length);
    if (type === "IHDR") {
      width = view.getUint32(offset + 8);
      height = view.getUint32(offset + 12);
    }
    if (type === "IDAT") idat.push(...data);
    offset += length + 12;
  }
  const rows = inflateSync(new Uint8Array(idat));
  const rgba = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) {
    const start = y * (width * 4 + 1) + 1;
    rgba.set(rows.subarray(start, start + width * 4), y * width * 4);
  }
  return { width, height, rgba };
}

function pngOfDataUrl(url: string): Pixels {
  const [, base64 = ""] = url.split(",");
  return decodePng(new Uint8Array(Buffer.from(base64, "base64")));
}

/** A canvas as a pixel store: drawing onto a clear canvas copies the image. */
class PixelCanvas {
  private pixels: Uint8ClampedArray;

  constructor(
    readonly width: number,
    readonly height: number,
  ) {
    this.pixels = new Uint8ClampedArray(width * height * 4);
  }

  getContext(kind: string) {
    if (kind !== "2d") return null;
    return {
      drawImage: (image: Pixels) => this.pixels.set(image.rgba),
      getImageData: () => ({
        width: this.width,
        height: this.height,
        data: new Uint8ClampedArray(this.pixels),
      }),
      putImageData: (image: { data: Uint8ClampedArray }) => this.pixels.set(image.data),
    };
  }

  async convertToBlob({ type }: { type: string }): Promise<Blob> {
    const bytes = encodePng(this.width, this.height, this.pixels);
    return new Blob([bytes.slice().buffer], { type });
  }
}

const decode = vi.fn(async (blob: Blob) => ({
  ...decodePng(new Uint8Array(await blob.arrayBuffer())),
  close: () => undefined,
}));

function withCanvas() {
  vi.stubGlobal("createImageBitmap", decode);
  vi.stubGlobal("OffscreenCanvas", PixelCanvas);
}

afterEach(() => {
  vi.unstubAllGlobals();
  decode.mockClear();
});

function imageFile(bytes: Uint8Array, name: string, type: string): File {
  return new File([bytes.slice().buffer], name, { type });
}

const CLEAR = [0, 0, 0, 0];
const BLACK = [0, 0, 0, 255];
const HALF_RED = [255, 0, 0, 128];

describe("ChatAttachmentAdapter", () => {
  const adapter = new ChatAttachmentAdapter(READER);

  it("offers images and PDFs only when the reader reads them", () => {
    expect(adapter.accept).toContain("image/png");
    expect(adapter.accept).toContain("application/pdf");
    expect(new ChatAttachmentAdapter(TEXT_ONLY).accept).toBe(
      ".csv,.tsv,.txt,text/csv,text/tab-separated-values,text/plain",
    );
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

  it("add() refuses a file over the per-file cap, naming its size", async () => {
    const file = new File([new Uint8Array(11 * 1024 * 1024)], "scan.png", {
      type: "image/png",
    });
    await expect(adapter.add({ file })).rejects.toThrow(
      "scan.png is 11.0 MB; one attachment can be at most 10 MB.",
    );
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
    expect(complete.content).toEqual([
      {
        type: "text",
        text: "Attached gene-ID list from controls.csv: PF3D7_0100100, PF3D7_0200200",
      },
    ]);
  });

  it("send() says so when nothing parses as gene IDs", async () => {
    const file = new File([""], "empty.csv", { type: "text/csv" });
    const complete = await adapter.send(pending(file));
    expect(complete.content).toEqual([
      {
        type: "text",
        text: "Attached file empty.csv contained no recognizable gene IDs.",
      },
    ]);
  });

  it("send() carries an opaque image inline as the file it is", async () => {
    withCanvas();
    const bytes = encodePng(2, 1, [...BLACK, ...BLACK]);
    const file = imageFile(bytes, "table.png", "image/png");
    const complete = await adapter.send(pending(file));
    expect(complete.content).toEqual([
      {
        type: "image",
        image: `data:image/png;base64,${Buffer.from(bytes).toString("base64")}`,
        filename: "table.png",
      },
    ]);
  });

  it("send() flattens a transparent image onto white before it is attached", async () => {
    withCanvas();
    const file = imageFile(
      encodePng(2, 2, [...CLEAR, ...BLACK, ...HALF_RED, ...CLEAR]),
      "table.png",
      "image/png",
    );
    const complete = await adapter.send(pending(file));
    const [part] = complete.content;
    expect(part?.type).toBe("image");
    const image = part?.type === "image" ? part.image : "";
    expect(image.startsWith("data:image/png;base64,")).toBe(true);
    const flat = pngOfDataUrl(image);
    expect([flat.width, flat.height]).toEqual([2, 2]);
    expect(Array.from(flat.rgba)).toEqual([
      ...[255, 255, 255, 255],
      ...BLACK,
      ...[255, 127, 127, 255],
      ...[255, 255, 255, 255],
    ]);
  });

  it("send() reads no pixels of a JPEG, which holds no alpha", async () => {
    withCanvas();
    const file = imageFile(new Uint8Array([0xff, 0xd8, 0xff]), "gel.jpg", "image/jpeg");
    const complete = await adapter.send(pending(file));
    expect(complete.content).toEqual([
      { type: "image", image: "data:image/jpeg;base64,/9j/", filename: "gel.jpg" },
    ]);
    expect(decode).not.toHaveBeenCalled();
  });

  it("send() refuses an image the browser cannot decode, naming it", async () => {
    withCanvas();
    const file = imageFile(PNG, "table.png", "image/png");
    await expect(adapter.send(pending(file))).rejects.toThrow(
      "Could not read table.png as an image.",
    );
  });

  it("send() carries a PDF inline as a file part", async () => {
    const file = new File(["%PDF"], "paper.pdf", { type: "application/pdf" });
    const complete = await adapter.send(pending(file));
    expect(complete.content).toEqual([
      {
        type: "file",
        data: "data:application/pdf;base64,JVBERg==",
        mimeType: "application/pdf",
        filename: "paper.pdf",
      },
    ]);
  });
});
