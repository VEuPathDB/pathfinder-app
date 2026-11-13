import { CircleHelp, Settings } from "lucide-react";
import Link from "next/link";

import { Button, buttonVariants } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { StrategistMark } from "@/lib/components/StrategistMark";
import { helpUrl } from "@/lib/routes";

export function RailFoot({ onOpenSettings }: { onOpenSettings: () => void }) {
  return (
    <div className="flex flex-col items-center gap-1">
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
        <TooltipContent side="right">Help</TooltipContent>
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
        <TooltipContent side="right">Settings</TooltipContent>
      </Tooltip>
      <StrategistMark />
    </div>
  );
}
