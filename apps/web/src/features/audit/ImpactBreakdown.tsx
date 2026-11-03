import { useId } from "react";
import type { FindingView } from "@pathfinder/shared/generated/types/FindingView";

import { Badge } from "@/components/ui/badge";

import { impactText } from "./format";
import { fallbackText, genomeUseText } from "./impactWords";
import { CERTAINTY_WORDS, IMPORTANCE_WORDS } from "./words";

export function ImpactBreakdown({ finding }: { finding: FindingView }) {
  const headingId = useId();
  const { weighing } = finding;
  if (weighing === null) {
    return (
      <section aria-labelledby={headingId} className="mt-4">
        <h2 id={headingId} className="text-sm font-semibold">
          Impact
        </h2>
        <p className="mt-1 text-xs">
          Not weighed: only a finding that names an error has an impact.
        </p>
      </section>
    );
  }
  const { importance, use } = weighing;
  const fallback = fallbackText(weighing);
  return (
    <section aria-labelledby={headingId} className="mt-4">
      <h2 id={headingId} className="text-sm font-semibold">
        {`Impact ${impactText(finding.impact)}`}
      </h2>
      <ul className="mt-1 space-y-0.5 text-xs">
        <li>
          {`Certainty: ${String(weighing.certaintyWeight)} (${CERTAINTY_WORDS[weighing.certainty].toLowerCase()})`}
        </li>
        <li>
          {`Gene importance: ${String(importance.value)}, because ${IMPORTANCE_WORDS[importance.source]} (${importance.genes.join(", ")})`}
        </li>
        <li>
          {`Genome use: ${String(use.value)}, because ${genomeUseText(use)} (${use.genome})`}
        </li>
      </ul>
      {fallback === null ? null : (
        <p className="mt-1 flex items-center gap-2 text-xs">
          <Badge variant="outline">Fallback</Badge>
          <span>{fallback}</span>
        </p>
      )}
    </section>
  );
}
