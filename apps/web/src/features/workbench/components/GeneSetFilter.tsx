"use client";

import { Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";

interface GeneSetFilterProps {
  value: string;
  onChange: (value: string) => void;
}

export function GeneSetFilter({ value, onChange }: GeneSetFilterProps) {
  return (
    <div className="relative">
      <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
      <Input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Filter gene sets..."
        className="bg-background py-1.5 pl-8 pr-8 text-xs"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          aria-label="Clear filter"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}
