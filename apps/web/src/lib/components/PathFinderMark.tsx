import Image from "next/image";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { withBasePath } from "@/lib/basePath";

export function PathFinderMark() {
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip tapToOpen>
        <TooltipTrigger asChild>
          <span
            role="img"
            aria-label="PathFinder"
            tabIndex={0}
            className="flex size-6 shrink-0 items-center justify-center rounded-md outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            <Image
              src={withBasePath("/pathfinder.svg")}
              alt=""
              width={16}
              height={16}
            />
          </span>
        </TooltipTrigger>
        <TooltipContent side="top">PathFinder</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
