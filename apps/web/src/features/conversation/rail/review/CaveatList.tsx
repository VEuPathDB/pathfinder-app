"use client";

import { ReviewSection } from "./ReviewSection";

export function CaveatList({ caveats }: { caveats: readonly string[] }) {
  if (caveats.length === 0) return null;
  return (
    <ReviewSection title="Caveats">
      <ul className="flex list-disc flex-col gap-1.5 pl-4 text-sm text-foreground marker:text-muted-foreground">
        {caveats.map((caveat, index) => (
          <li key={`${index}:${caveat}`}>{caveat}</li>
        ))}
      </ul>
    </ReviewSection>
  );
}
