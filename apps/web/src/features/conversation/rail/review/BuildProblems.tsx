"use client";

import { cn } from "@/lib/utils/cn";

import type { BuildProblem } from "./reviewModel";
import { ReviewSection } from "./ReviewSection";

export function BuildProblems({ problems }: { problems: readonly BuildProblem[] }) {
  if (problems.length === 0) return null;
  return (
    <ReviewSection title="Build problems">
      <ul className="flex flex-col gap-2">
        {problems.map((problem) => (
          <li key={problem.key} className="flex flex-col gap-0.5">
            <span className="text-sm text-foreground">{problem.step}</span>
            <span
              className={cn(
                "text-xs",
                problem.status === "failed" ? "text-destructive" : "text-warning",
              )}
            >
              {problem.sentence}
            </span>
          </li>
        ))}
      </ul>
    </ReviewSection>
  );
}
