/**
 * @vitest-environment jsdom
 */
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import served from "../../../../../packages/spec/audit_words.json";
import { server } from "../../../vitest.msw-setup";
import { auditWordsOptions, getAuditWords } from "./audits";

const WORDS_URL = "http://localhost:3000/pathfinder/api/v1/audits/words";

describe("getAuditWords", () => {
  it("reads the words the API serves for every audit value", async () => {
    server.use(http.get(WORDS_URL, () => HttpResponse.json(served)));

    const words = await getAuditWords();

    expect(words).toEqual(served);
    expect(words.checks.gene_length).toBe("Gene length against orthologs");
    expect(words.halts.sign_in).toBe(
      "The audit needs your VEuPathDB sign-in. Sign in on the site, then resume it.",
    );
  });

  it("refuses a body that leaves a value without words", async () => {
    const { sign_in: _dropped, ...halts } = served.halts;
    server.use(http.get(WORDS_URL, () => HttpResponse.json({ ...served, halts })));

    await expect(getAuditWords()).rejects.toThrow("/api/v1/audits/words");
  });
});

describe("auditWordsOptions", () => {
  it("reads the words once, since a deployment serves one set", () => {
    const options = auditWordsOptions();

    expect(options.queryKey).toEqual(["audits", "words"]);
    expect(options.staleTime).toBe(Infinity);
  });
});
