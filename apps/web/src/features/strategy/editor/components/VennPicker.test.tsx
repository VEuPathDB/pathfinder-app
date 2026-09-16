/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { VennPicker } from "./VennPicker";

// Match the debounce window declared in VennPicker.
const ON_CHANGE_DEBOUNCE_MS = 600;

afterEach(cleanup);

describe("VennPicker", () => {
  it("renders three clickable region paths", () => {
    render(<VennPicker operator="INTERSECT" onChange={() => {}} />);
    expect(screen.getByLabelText("A only")).toBeTruthy();
    expect(screen.getByLabelText("Intersection region")).toBeTruthy();
    expect(screen.getByLabelText("B only")).toBeTruthy();
  });

  describe("click cycling (debounced - only the final operator reaches onChange)", () => {
    beforeEach(() => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
    });
    afterEach(() => {
      vi.useRealTimers();
    });

    it("single click on A fires LONLY after the debounce window", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      const onChange = vi.fn();
      render(<VennPicker operator="INTERSECT" onChange={onChange} />);
      await user.click(screen.getByLabelText("A only"));
      expect(onChange).not.toHaveBeenCalled(); // debounced
      vi.advanceTimersByTime(ON_CHANGE_DEBOUNCE_MS + 50);
      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenLastCalledWith("LONLY");
    });

    it("two rapid clicks on A coalesce into a single MINUS push", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      const onChange = vi.fn();
      render(<VennPicker operator="INTERSECT" onChange={onChange} />);
      const a = screen.getByLabelText("A only");
      await user.click(a);
      await user.click(a);
      vi.advanceTimersByTime(ON_CHANGE_DEBOUNCE_MS + 50);
      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenLastCalledWith("MINUS");
    });

    it("three rapid clicks on A wrap back to LONLY (single coalesced push)", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      const onChange = vi.fn();
      render(<VennPicker operator="INTERSECT" onChange={onChange} />);
      const a = screen.getByLabelText("A only");
      await user.click(a);
      await user.click(a);
      await user.click(a);
      vi.advanceTimersByTime(ON_CHANGE_DEBOUNCE_MS + 50);
      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenLastCalledWith("LONLY");
    });

    it("after the cycling window closes, the next click is a fresh first click", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      const onChange = vi.fn();
      render(<VennPicker operator="INTERSECT" onChange={onChange} />);
      const a = screen.getByLabelText("A only");
      await user.click(a);
      await user.click(a);
      vi.advanceTimersByTime(1100); // > 1s cycling window AND > debounce
      expect(onChange).toHaveBeenLastCalledWith("MINUS");
      onChange.mockClear();
      await user.click(a);
      vi.advanceTimersByTime(ON_CHANGE_DEBOUNCE_MS + 50);
      expect(onChange).toHaveBeenLastCalledWith("LONLY");
    });

    it("two rapid clicks on lens coalesce into a single UNION push", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      const onChange = vi.fn();
      render(<VennPicker operator="MINUS" onChange={onChange} />);
      const lens = screen.getByLabelText("Intersection region");
      await user.click(lens);
      await user.click(lens);
      vi.advanceTimersByTime(ON_CHANGE_DEBOUNCE_MS + 50);
      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenLastCalledWith("UNION");
    });

    it("two rapid clicks on B coalesce into a single RMINUS push", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      const onChange = vi.fn();
      render(<VennPicker operator="INTERSECT" onChange={onChange} />);
      const b = screen.getByLabelText("B only");
      await user.click(b);
      await user.click(b);
      vi.advanceTimersByTime(ON_CHANGE_DEBOUNCE_MS + 50);
      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenLastCalledWith("RMINUS");
    });

    it("clicking a different region resets the cycle counter (final wins after debounce)", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      const onChange = vi.fn();
      render(<VennPicker operator="INTERSECT" onChange={onChange} />);
      await user.click(screen.getByLabelText("A only"));
      await user.click(screen.getByLabelText("B only"));
      vi.advanceTimersByTime(ON_CHANGE_DEBOUNCE_MS + 50);
      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenLastCalledWith("RONLY");
    });
  });

  describe("Colocate + Swap (deliberate single actions - bypass debounce)", () => {
    beforeEach(() => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
    });
    afterEach(() => {
      vi.useRealTimers();
    });

    it("clicking Colocate fires COLOCATE after the debounce window", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      const onChange = vi.fn();
      render(<VennPicker operator="INTERSECT" onChange={onChange} />);
      await user.click(screen.getByLabelText("Colocate"));
      vi.advanceTimersByTime(ON_CHANGE_DEBOUNCE_MS + 50);
      expect(onChange).toHaveBeenCalledWith("COLOCATE");
    });

    it("Swap fires immediately (no debounce - flushed by the swap handler)", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      const onChange = vi.fn();
      render(<VennPicker operator="MINUS" onChange={onChange} />);
      await user.click(screen.getByRole("button", { name: /swap/i }));
      // Swap calls onChange directly without waiting for debounce.
      expect(onChange).toHaveBeenCalledWith("RMINUS");
    });

    it("Swap toggles LONLY↔RONLY immediately", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      const onChange = vi.fn();
      render(<VennPicker operator="LONLY" onChange={onChange} />);
      await user.click(screen.getByRole("button", { name: /swap/i }));
      expect(onChange).toHaveBeenCalledWith("RONLY");
    });
  });

  it("readout reflects current operator", () => {
    render(<VennPicker operator="INTERSECT" onChange={() => {}} />);
    expect(screen.getByText(/INTERSECT/)).toBeTruthy();
  });

  it("readout renders LONLY as 'Just A'", () => {
    render(<VennPicker operator="LONLY" onChange={() => {}} />);
    expect(screen.getByText(/Just A/i)).toBeTruthy();
  });

  it("renders custom A/B labels in readout", () => {
    render(
      <VennPicker
        operator="MINUS"
        onChange={() => {}}
        aLabel="Step 1"
        bLabel="Step 2"
      />,
    );
    expect(screen.getByText(/Step 1/)).toBeTruthy();
  });

  it("region paths anchor at the circle intersection points (not top/bottom)", () => {
    render(<VennPicker operator="INTERSECT" onChange={() => {}} />);
    for (const label of ["A only", "Intersection region", "B only"]) {
      const d = screen.getByLabelText(label).getAttribute("d") ?? "";
      expect(d.startsWith("M 140 35.74")).toBe(true);
      expect(d).toContain("140 144.26");
    }
  });

  describe("visual highlighting", () => {
    it("LONLY fills the A circle, regions stay transparent", () => {
      const { container } = render(<VennPicker operator="LONLY" onChange={() => {}} />);
      const fills = Array.from(container.querySelectorAll("circle[fill*='primary']"));
      const aFill = fills.find((c) => c.getAttribute("cx") === "110");
      const bFill = fills.find((c) => c.getAttribute("cx") === "170");
      expect(aFill?.getAttribute("fill-opacity")).toBe("1");
      expect(bFill?.getAttribute("fill-opacity")).toBe("0");
      for (const label of ["A only", "Intersection region", "B only"]) {
        expect(screen.getByLabelText(label).getAttribute("class") ?? "").toContain(
          "fill-transparent",
        );
      }
    });

    it("RONLY fills the B circle, regions stay transparent", () => {
      const { container } = render(<VennPicker operator="RONLY" onChange={() => {}} />);
      const fills = Array.from(container.querySelectorAll("circle[fill*='primary']"));
      const aFill = fills.find((c) => c.getAttribute("cx") === "110");
      const bFill = fills.find((c) => c.getAttribute("cx") === "170");
      expect(aFill?.getAttribute("fill-opacity")).toBe("0");
      expect(bFill?.getAttribute("fill-opacity")).toBe("1");
    });

    it("UNION fills both circles, regions stay transparent", () => {
      const { container } = render(<VennPicker operator="UNION" onChange={() => {}} />);
      const fills = Array.from(container.querySelectorAll("circle[fill*='primary']"));
      expect(fills.every((c) => c.getAttribute("fill-opacity") === "1")).toBe(true);
      for (const label of ["A only", "Intersection region", "B only"]) {
        expect(screen.getByLabelText(label).getAttribute("class") ?? "").toContain(
          "fill-transparent",
        );
      }
    });

    it("INTERSECT fills the lens region, A and B regions transparent", () => {
      render(<VennPicker operator="INTERSECT" onChange={() => {}} />);
      expect(
        screen.getByLabelText("Intersection region").getAttribute("class") ?? "",
      ).toContain("fill-[hsl(var(--primary)/0.55)]");
      expect(screen.getByLabelText("A only").getAttribute("class") ?? "").toContain(
        "fill-transparent",
      );
      expect(screen.getByLabelText("B only").getAttribute("class") ?? "").toContain(
        "fill-transparent",
      );
    });

    it("MINUS fills the A crescent only", () => {
      render(<VennPicker operator="MINUS" onChange={() => {}} />);
      expect(screen.getByLabelText("A only").getAttribute("class") ?? "").toContain(
        "fill-[hsl(var(--primary)/0.55)]",
      );
      expect(
        screen.getByLabelText("Intersection region").getAttribute("class") ?? "",
      ).toContain("fill-transparent");
    });
  });
});
