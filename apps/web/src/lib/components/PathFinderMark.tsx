import { useQuery } from "@tanstack/react-query";
import { healthCheckQueryOptions } from "@pathfinder/shared/generated/hooks/useHealthCheck";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { PathFinderLogo } from "@/lib/components/PathFinderLogo";

export function PathFinderMark() {
  const { data } = useQuery(healthCheckQueryOptions());
  const name = data === undefined ? "PathFinder" : `PathFinder v${data.version}`;
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip tapToOpen>
        <TooltipTrigger asChild>
          <span
            role="img"
            aria-label="PathFinder"
            tabIndex={0}
            className="flex size-9 shrink-0 items-center justify-center rounded-md outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            <PathFinderLogo size={22} />
          </span>
        </TooltipTrigger>
        <TooltipContent side="left">{name}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
