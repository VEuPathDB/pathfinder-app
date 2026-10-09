import Image from "next/image";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { withBasePath } from "@/lib/basePath";

export function RailLogo() {
  return (
    <Tooltip tapToOpen>
      <TooltipTrigger asChild>
        <span
          role="img"
          aria-label="PathFinder"
          tabIndex={0}
          className="flex size-9 items-center justify-center rounded-md outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          <Image src={withBasePath("/pathfinder.svg")} alt="" width={22} height={22} />
        </span>
      </TooltipTrigger>
      <TooltipContent side="right">PathFinder</TooltipContent>
    </Tooltip>
  );
}
