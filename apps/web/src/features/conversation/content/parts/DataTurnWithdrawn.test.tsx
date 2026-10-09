/**
 * @vitest-environment jsdom
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataTurnWithdrawn } from "./DataTurnWithdrawn";

const NOTICE =
  "Claude Sonnet 5.5 declined this request. Its provider's biological safety filters blocked it. These filters sometimes block legitimate research questions (false positives). Try rephrasing it, or pick a different model in Settings.";

describe("DataTurnWithdrawn", () => {
  it("says the request was declined, in the words the backend sent", () => {
    render(<DataTurnWithdrawn data={{ errorText: NOTICE, messageId: "u1" }} />);

    const notice = screen.getByTestId("failure-notice");
    expect(notice).toHaveTextContent("Request declined");
    expect(notice).toHaveTextContent(NOTICE);
  });

  it("offers no retry, which would send the declined words again", () => {
    render(<DataTurnWithdrawn data={{ errorText: NOTICE, messageId: "u1" }} />);

    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});
