import type { StrategyLink } from "@pathfinder/shared";

import { Figure } from "@/features/conversation/thread/Figure";

export function DataStrategyLink({ data }: { data: StrategyLink }) {
  const name = data.title ?? `Strategy ${data.strategyId}`;
  return (
    <Figure testId="data-strategy-link" title="Strategy" caption={name}>
      <div className="text-sm">
        <a
          href={data.url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-primary underline-offset-2 hover:underline"
        >
          {name}
        </a>
      </div>
    </Figure>
  );
}
