/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { buildUrl } from "@/lib/api/http";

import { SAMPLE_FINDINGS, SAMPLE_RUN_ID } from "./__fixtures__/sampleRun";
import { DownloadFindings } from "./DownloadFindings";

describe("DownloadFindings", () => {
  it("links to the run's findings as CSV", () => {
    render(<DownloadFindings runId={SAMPLE_RUN_ID} total={SAMPLE_FINDINGS.total} />);
    const link = screen.getByRole("link", {
      name: `Download the ${String(SAMPLE_FINDINGS.total)} findings of this audit as a spreadsheet (CSV)`,
    });
    expect(link).toHaveAttribute(
      "href",
      buildUrl(`/api/v1/audits/${SAMPLE_RUN_ID}/findings.csv`),
    );
    expect(link).toHaveAttribute("download");
    expect(link).toHaveTextContent("Download findings (CSV)");
  });

  it("offers nothing to download when the run holds no finding", () => {
    const { container } = render(<DownloadFindings runId={SAMPLE_RUN_ID} total={0} />);
    expect(container).toBeEmptyDOMElement();
  });
});
