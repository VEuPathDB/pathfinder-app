import { CircleHelp, Settings } from "lucide-react";
import Link from "next/link";

import { Button, buttonVariants } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { PathFinderMark } from "@/lib/components/PathFinderMark";
import { helpUrl } from "@/lib/routes";

export function RailFoot({ onOpenSettings }: { onOpenSettings: () => void }) {
  return (
    <TooltipProvider delayDuration={150}>
      <div data-rail-foot className="mt-auto flex flex-col items-center gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Link
              href={helpUrl()}
              aria-label="Help"
              className={buttonVariants({ variant: "ghost", size: "icon" })}
            >
              <CircleHelp className="h-4 w-4" aria-hidden />
            </Link>
          </TooltipTrigger>
          <TooltipContent side="left">Help</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onOpenSettings()}
              aria-label="Settings"
              data-testid="settings-button"
            >
              <Settings className="h-4 w-4" aria-hidden />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="left">Settings</TooltipContent>
        </Tooltip>
        <PathFinderMark />
      </div>
    </TooltipProvider>
  );
}
