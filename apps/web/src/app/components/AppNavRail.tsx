"use client";

import { Bookmark, ClipboardCheck, MessageCircle, PanelLeft } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils/cn";

const ACTIVE_PILL = "bg-primary/15 text-primary hover:bg-primary/20 hover:text-primary";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { auditsUrl, chatRoot, savedUrl } from "@/lib/routes";

import { RailQuotaMeter } from "./RailQuotaMeter";

interface AppNavRailProps {
  siteId: string;
  onToggleSidebar: () => void;
  sidebarExpanded: boolean;
}

interface NavSpec {
  href: string;
  icon: LucideIcon;
  label: string;
}

const NAV: NavSpec[] = [
  { href: chatRoot(), icon: MessageCircle, label: "Conversation" },
  { href: savedUrl(), icon: Bookmark, label: "Saved strategies" },
  { href: auditsUrl(), icon: ClipboardCheck, label: "Audits" },
];

export function AppNavRail({
  siteId,
  onToggleSidebar,
  sidebarExpanded,
}: AppNavRailProps) {
  const pathname = usePathname();

  return (
    <TooltipProvider delayDuration={150}>
      <div className="flex h-full w-11 shrink-0 flex-col items-center gap-1 border-r border-border bg-sidebar py-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={onToggleSidebar}
              aria-label={
                sidebarExpanded
                  ? "Collapse conversation sidebar"
                  : "Open conversation sidebar"
              }
              aria-pressed={sidebarExpanded}
              className={cn(sidebarExpanded && ACTIVE_PILL)}
            >
              <PanelLeft className="h-4 w-4" aria-hidden />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">
            {sidebarExpanded ? "Hide conversations" : "Show conversations"}
          </TooltipContent>
        </Tooltip>

        <div className="my-1 h-px w-6 bg-border" />

        {NAV.map((item) => {
          const href = item.href;
          const active = pathname.startsWith(href);
          const Icon = item.icon;
          return (
            <Tooltip key={item.href}>
              <TooltipTrigger asChild>
                <Link
                  href={href}
                  aria-label={item.label}
                  aria-current={active ? "page" : undefined}
                  onClick={(event) => {
                    // The reader is already in this section; a re-navigation
                    // would drop the open conversation for the draft route.
                    if (active) event.preventDefault();
                  }}
                  className={cn(
                    buttonVariants({ variant: "ghost", size: "icon" }),
                    active && ACTIVE_PILL,
                  )}
                >
                  <Icon className="h-4 w-4" aria-hidden />
                </Link>
              </TooltipTrigger>
              <TooltipContent side="right">{item.label}</TooltipContent>
            </Tooltip>
          );
        })}

        <div className="mt-auto flex flex-col items-center gap-1">
          <RailQuotaMeter siteId={siteId} />
        </div>
      </div>
    </TooltipProvider>
  );
}
