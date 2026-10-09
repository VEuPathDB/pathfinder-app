/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TooltipProvider } from "@/components/ui/tooltip";

import { RailLogo } from "./RailLogo";

describe("RailLogo", () => {
  it("names the product on a touch tap", async () => {
    render(
      <TooltipProvider>
        <RailLogo />
      </TooltipProvider>,
    );

    await userEvent.pointer({
      keys: "[TouchA]",
      target: screen.getByRole("img", { name: "PathFinder" }),
    });

    expect(await screen.findByRole("tooltip")).toHaveTextContent("PathFinder");
  });
});
