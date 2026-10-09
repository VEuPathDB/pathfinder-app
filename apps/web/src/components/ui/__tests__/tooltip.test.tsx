/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

function renderTooltip({ tapToOpen }: { tapToOpen: boolean }) {
  const user = userEvent.setup();
  render(
    <TooltipProvider>
      <Tooltip tapToOpen={tapToOpen}>
        <TooltipTrigger asChild>
          <button type="button">Spend</button>
        </TooltipTrigger>
        <TooltipContent>Three dollars this month</TooltipContent>
      </Tooltip>
      <p>Elsewhere</p>
    </TooltipProvider>,
  );
  return { user, trigger: screen.getByRole("button", { name: "Spend" }) };
}

async function expectClosed(trigger: HTMLElement) {
  await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
  expect(trigger).toHaveAttribute("data-state", "closed");
}

describe("Tooltip with tap to open", () => {
  it("opens on a touch tap and links the content to its trigger", async () => {
    const { user, trigger } = renderTooltip({ tapToOpen: true });

    await user.pointer({ keys: "[TouchA]", target: trigger });

    const tip = await screen.findByRole("tooltip");
    expect(tip).toHaveTextContent("Three dollars this month");
    expect(trigger).toHaveAttribute("aria-describedby", tip.id);
  });

  it("opens on a pen tap", async () => {
    const { trigger } = renderTooltip({ tapToOpen: true });

    fireEvent.pointerDown(trigger, { pointerType: "pen" });
    fireEvent.pointerUp(trigger, { pointerType: "pen" });
    fireEvent.click(trigger);

    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      "Three dollars this month",
    );
  });

  it("stays closed when the touch becomes a scroll", async () => {
    const { trigger } = renderTooltip({ tapToOpen: true });

    fireEvent.pointerDown(trigger, { pointerType: "touch" });
    fireEvent.pointerCancel(trigger, { pointerType: "touch" });
    fireEvent.pointerUp(trigger, { pointerType: "touch" });

    await expectClosed(trigger);
  });

  it("closes on a second tap of the trigger", async () => {
    const { user, trigger } = renderTooltip({ tapToOpen: true });
    await user.pointer({ keys: "[TouchA]", target: trigger });
    await screen.findByRole("tooltip");

    await user.pointer({ keys: "[TouchA]", target: trigger });

    await expectClosed(trigger);
  });

  it("closes on a tap outside the trigger", async () => {
    const { user, trigger } = renderTooltip({ tapToOpen: true });
    await user.pointer({ keys: "[TouchA]", target: trigger });
    await screen.findByRole("tooltip");

    await user.pointer({ keys: "[TouchA]", target: screen.getByText("Elsewhere") });

    await expectClosed(trigger);
  });

  it("leaves only the second tooltip open after tapping two triggers", async () => {
    const user = userEvent.setup();
    render(
      <TooltipProvider>
        <Tooltip tapToOpen>
          <TooltipTrigger asChild>
            <button type="button">Spend</button>
          </TooltipTrigger>
          <TooltipContent>Three dollars this month</TooltipContent>
        </Tooltip>
        <Tooltip tapToOpen>
          <TooltipTrigger asChild>
            <button type="button">Tokens</button>
          </TooltipTrigger>
          <TooltipContent>Nine thousand tokens</TooltipContent>
        </Tooltip>
      </TooltipProvider>,
    );
    const spend = screen.getByRole("button", { name: "Spend" });
    const tokens = screen.getByRole("button", { name: "Tokens" });
    await user.pointer({ keys: "[TouchA]", target: spend });
    await screen.findByRole("tooltip");

    await user.pointer({ keys: "[TouchA]", target: tokens });

    await waitFor(() =>
      expect(screen.getAllByRole("tooltip").map((tip) => tip.textContent)).toEqual([
        "Nine thousand tokens",
      ]),
    );
    expect(spend).toHaveAttribute("data-state", "closed");
  });

  it("opens on a tap of a span that wraps a disabled button", async () => {
    const user = userEvent.setup();
    render(
      <TooltipProvider>
        <Tooltip tapToOpen>
          <TooltipTrigger asChild>
            <span data-testid="row">
              <button type="button" disabled>
                Clear
              </button>
            </span>
          </TooltipTrigger>
          <TooltipContent>No strategy yet</TooltipContent>
        </Tooltip>
      </TooltipProvider>,
    );

    await user.pointer({
      keys: "[TouchA]",
      target: screen.getByRole("button", { name: "Clear" }),
    });

    const tip = await screen.findByRole("tooltip");
    expect(within(tip).getByText("No strategy yet")).toBeVisible();
  });

  it("opens on mouse hover", async () => {
    const { user, trigger } = renderTooltip({ tapToOpen: true });

    await user.hover(trigger);

    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      "Three dollars this month",
    );
  });

  it("closes on a mouse click after hover", async () => {
    const { user, trigger } = renderTooltip({ tapToOpen: true });

    await user.click(trigger);

    await expectClosed(trigger);
  });

  it("opens on keyboard focus and closes on Escape", async () => {
    const { user, trigger } = renderTooltip({ tapToOpen: true });

    await user.tab();
    expect(trigger).toHaveFocus();
    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      "Three dollars this month",
    );

    await user.keyboard("{Escape}");
    await expectClosed(trigger);
  });
});

describe("Tooltip on an action trigger", () => {
  it("leaves no tooltip open after a touch tap", async () => {
    const { user, trigger } = renderTooltip({ tapToOpen: false });

    await user.pointer({ keys: "[TouchA]", target: trigger });

    await expectClosed(trigger);
  });

  it("opens on mouse hover", async () => {
    const { user, trigger } = renderTooltip({ tapToOpen: false });

    await user.hover(trigger);

    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      "Three dollars this month",
    );
  });

  it("opens on keyboard focus and closes on Escape", async () => {
    const { user, trigger } = renderTooltip({ tapToOpen: false });

    await user.tab();
    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      "Three dollars this month",
    );

    await user.keyboard("{Escape}");
    await expectClosed(trigger);
  });
});
