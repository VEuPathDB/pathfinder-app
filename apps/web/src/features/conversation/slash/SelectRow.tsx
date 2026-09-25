"use client";

import type { KeyboardEvent } from "react";

import type { ParamDef } from "./types";

type SelectParam = Extract<ParamDef, { kind: "select" }>;

interface SelectRowProps {
  param: SelectParam;
  onSubmit: (value: string) => void;
}

/** Arrow keys move focus between the options; Enter picks the focused one. */
function moveFocus(event: KeyboardEvent<HTMLDivElement>): void {
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  event.preventDefault();
  const options = Array.from(event.currentTarget.querySelectorAll("button"));
  const current = options.findIndex((o) => o === document.activeElement);
  const step = event.key === "ArrowDown" ? 1 : -1;
  options[(current + step + options.length) % options.length]?.focus();
}

export function SelectRow({ param, onSubmit }: SelectRowProps) {
  return (
    <div>
      <div className="px-3 py-2 text-xs font-medium text-foreground">{param.label}</div>
      <div
        role="group"
        aria-label={param.label}
        className="max-h-60 overflow-y-auto"
        onKeyDown={moveFocus}
      >
        {param.options.map((opt, i) => (
          <button
            key={opt.value}
            type="button"
            autoFocus={i === 0}
            onClick={() => onSubmit(opt.value)}
            data-testid={`slash-param-option-${opt.value}`}
            className="flex w-full px-3 py-2 text-left text-sm font-medium text-foreground outline-none hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}
