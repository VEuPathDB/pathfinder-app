import { useQuery } from "@tanstack/react-query";
import { healthCheckQueryOptions } from "@strategist/shared/generated/hooks/useHealthCheck";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { StrategistLogo } from "@/lib/components/StrategistLogo";

export function StrategistMark() {
  const { data } = useQuery(healthCheckQueryOptions());
  const name = data === undefined ? "Strategist" : `Strategist v${data.version}`;
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip tapToOpen>
        <TooltipTrigger asChild>
          <span
            role="img"
            aria-label="VEuPathDB Strategist"
            tabIndex={0}
            className="flex size-9 shrink-0 items-center justify-center rounded-md outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            <StrategistLogo size={22} />
          </span>
        </TooltipTrigger>
        <TooltipContent side="left">{name}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
