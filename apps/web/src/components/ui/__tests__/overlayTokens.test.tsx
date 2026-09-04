/**
 * @vitest-environment jsdom
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { AlertDialog, AlertDialogContent } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Slider } from "@/components/ui/slider";

const SCRIM = "bg-foreground/50";

describe("overlay scrims", () => {
  it("uses one scrim value for the dialog", () => {
    render(
      <Dialog open>
        <DialogContent>
          <DialogTitle>Title</DialogTitle>
        </DialogContent>
      </Dialog>,
    );
    const overlay = document.querySelector('[data-slot="dialog-overlay"]');
    expect(overlay).toHaveClass(SCRIM);
    expect(overlay?.className).not.toContain("bg-black");
  });

  it("uses the same scrim value for the alert dialog", () => {
    render(
      <AlertDialog open>
        <AlertDialogContent>body</AlertDialogContent>
      </AlertDialog>,
    );
    const overlay = document.querySelector('[data-slot="alert-dialog-overlay"]');
    expect(overlay).toHaveClass(SCRIM);
    expect(overlay?.className).not.toContain("bg-black");
  });

  it("uses the same scrim value for the sheet", () => {
    render(
      <Sheet open>
        <SheetContent>
          <SheetTitle>Title</SheetTitle>
        </SheetContent>
      </Sheet>,
    );
    const overlay = document.querySelector('[data-slot="sheet-overlay"]');
    expect(overlay).toHaveClass(SCRIM);
    expect(overlay?.className).not.toContain("bg-black");
  });
});

describe("every scrim in the app", () => {
  it("fades the foreground by the one value", () => {
    const root = `${join(process.cwd(), "src")}/`;
    const found: string[] = [];
    const walk = (dir: string): void => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, entry.name);
        if (entry.isDirectory()) {
          if (entry.name === "generated" || entry.name === "node_modules") continue;
          walk(full);
          continue;
        }
        if (!/\.tsx$/.test(entry.name) || /\.test\.tsx$/.test(entry.name)) continue;
        for (const match of readFileSync(full, "utf8").matchAll(
          /bg-foreground\/(\d+)/g,
        )) {
          found.push(`${full.slice(root.length)}: ${match[0]}`);
        }
      }
    };
    walk(root);
    const files = new Set(found.map((line) => line.split(":")[0]));
    expect(files).toContain("components/ui/dialog.tsx");
    expect(files).toContain("components/ui/alert-dialog.tsx");
    expect(files).toContain("components/ui/sheet.tsx");
    expect(found.filter((line) => !line.endsWith(SCRIM))).toEqual([]);
  });
});

describe("destructive foreground", () => {
  it("labels a destructive badge with the destructive foreground token", () => {
    render(<Badge variant="destructive">Danger</Badge>);
    const badge = screen.getByText("Danger");
    expect(badge).toHaveClass("text-destructive-foreground");
    expect(badge.className).not.toContain("text-white");
    expect(badge.className).not.toContain("dark:bg-destructive");
  });

  it("labels a destructive button with the destructive foreground token", () => {
    render(<Button variant="destructive">Delete</Button>);
    const button = screen.getByRole("button", { name: "Delete" });
    expect(button).toHaveClass("text-destructive-foreground");
    expect(button.className).not.toContain("text-white");
    expect(button.className).not.toContain("dark:bg-destructive");
  });
});

describe("slider thumb", () => {
  it("fills the thumb from the card token", () => {
    render(<Slider defaultValue={[50]} />);
    const thumb = document.querySelector('[data-slot="slider-thumb"]');
    expect(thumb).toHaveClass("bg-card");
    expect(thumb?.className).not.toContain("bg-white");
  });
});
