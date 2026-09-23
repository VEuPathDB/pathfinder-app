"use client";

import type { StrategyLink } from "@pathfinder/shared";

import { Figure } from "@/features/conversation/thread/Figure";
import { useSiteLinkTarget } from "@/lib/hooks/useSiteLinkTarget";

export function DataStrategyLink({ data }: { data: StrategyLink }) {
  const name = data.title ?? `Strategy ${data.strategyId}`;
  const target = useSiteLinkTarget();
  return (
    <Figure testId="data-strategy-link" title="Strategy" caption={name}>
      <div className="text-sm">
        <a
          href={data.url}
          target={target}
          rel="noopener noreferrer"
          className="font-medium text-primary underline-offset-2 hover:underline"
        >
          {name}
        </a>
      </div>
    </Figure>
  );
}
