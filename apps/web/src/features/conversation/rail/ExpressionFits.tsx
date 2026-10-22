import { useId, type ReactElement } from "react";
import type { EvidenceCard, ExpressionFit } from "@pathfinder/shared";

const LABEL = "Phyletic pattern, checked on each step's first groups";

function fitLine(fit: ExpressionFit, title: string | undefined): string {
  if (title !== undefined) return `${title}: ${fit.sentence}`;
  return fit.sentence.charAt(0).toUpperCase() + fit.sentence.slice(1);
}

export function ExpressionFits({ card }: { card: EvidenceCard }): ReactElement | null {
  const labelId = useId();
  const fits = card.expressionFits ?? [];
  if (fits.length === 0) return null;
  const titles = new Map(card.steps.map((step) => [step.wdkStepId, step.title]));
  return (
    <div className="text-[11px]">
      <p id={labelId} className="text-muted-foreground">
        {LABEL}
      </p>
      <ul role="list" aria-labelledby={labelId} className="space-y-0.5">
        {fits.map((fit) => (
          <li key={fit.wdkStepId} data-testid="evidence-expression-fit">
            {fitLine(fit, titles.get(fit.wdkStepId))}
          </li>
        ))}
      </ul>
    </div>
  );
}
