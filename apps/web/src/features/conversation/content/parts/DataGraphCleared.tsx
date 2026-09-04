import type { GraphCleared } from "@pathfinder/shared";

import { Figure } from "@/features/conversation/thread/Figure";

const CLEARED = "Strategy cleared";

export function DataGraphCleared({ data }: { data: GraphCleared }) {
  const reason = data.reason ?? "";
  return (
    <Figure
      testId="data-graph-cleared"
      title={null}
      caption={reason.length > 0 ? `${CLEARED} - ${reason}` : CLEARED}
    >
      {null}
    </Figure>
  );
}
