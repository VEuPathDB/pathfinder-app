"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";

import type { ParamDef } from "./types";

export function TextRow({
  param,
  onSubmit,
}: {
  param: Extract<ParamDef, { kind: "text" }>;
  onSubmit: (value: string) => void;
}) {
  const [value, setValue] = useState("");
  return (
    <div className="flex flex-col gap-2 p-3">
      <label className="text-xs font-medium text-foreground">{param.label}</label>
      <input
        type="text"
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            onSubmit(value);
          }
        }}
        placeholder={param.placeholder}
        data-testid={`slash-param-text-${param.name}`}
        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
      />
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() => onSubmit(value)}
        className="self-end"
      >
        Next
      </Button>
    </div>
  );
}

export function TextAreaRow({
  param,
  onSubmit,
}: {
  param: Extract<ParamDef, { kind: "textarea" }>;
  onSubmit: (value: string) => void;
}) {
  const [value, setValue] = useState("");
  return (
    <div className="flex flex-col gap-2 p-3">
      <label className="text-xs font-medium text-foreground">{param.label}</label>
      <textarea
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        rows={param.rows ?? 4}
        placeholder={param.placeholder}
        data-testid={`slash-param-textarea-${param.name}`}
        className="w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
      />
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() => onSubmit(value)}
        className="self-end"
      >
        Continue
      </Button>
    </div>
  );
}
