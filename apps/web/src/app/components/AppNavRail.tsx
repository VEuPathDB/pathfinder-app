"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { siteShortName } from "@pathfinder/shared";
import {
  AlertTriangle,
  Bookmark,
  Brain,
  MessageCircle,
  PanelLeft,
  Settings,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils/cn";

const ACTIVE_PILL = "bg-primary/15 text-primary hover:bg-primary/20 hover:text-primary";
const CANNOT_REACH = "Couldn't reach";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { SiteIcon } from "@/features/sites/components/SiteIcon";
import { sitesOptions } from "@/lib/api/sites";
import { siteIsDown } from "@/lib/sites/availability";
import { useSessionStore } from "@/state/useSessionStore";

interface AppNavRailProps {
  siteId: string;
  onSiteChange: (siteId: string) => void;
  onOpenSettings: () => void;
  onOpenModelSettings: () => void;
  onToggleSidebar: () => void;
  sidebarExpanded: boolean;
}

interface NavSpec {
  slug: "conversation" | "saved";
  icon: LucideIcon;
  label: string;
}

const NAV: NavSpec[] = [
  { slug: "conversation", icon: MessageCircle, label: "Conversation" },
  { slug: "saved", icon: Bookmark, label: "Saved strategies" },
];

export function AppNavRail({
  siteId,
  onSiteChange,
  onOpenSettings,
  onOpenModelSettings,
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
          const href = `/${siteId}/${item.slug}`;
          const active = pathname.startsWith(href);
          const Icon = item.icon;
          return (
            <Tooltip key={item.slug}>
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
          <SiteSwitcherButton siteId={siteId} onChange={onSiteChange} />

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={onOpenModelSettings}
                aria-label="AI model settings"
                data-testid="nav-rail-ai-button"
              >
                <Brain className="h-4 w-4" aria-hidden />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">AI model</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={onOpenSettings}
                aria-label="Settings"
                data-testid="nav-rail-settings-button"
              >
                <Settings className="h-4 w-4" aria-hidden />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">Settings</TooltipContent>
          </Tooltip>
        </div>
      </div>
    </TooltipProvider>
  );
}

function SiteSwitcherButton({
  siteId,
  onChange,
}: {
  siteId: string;
  onChange: (id: string) => void;
}) {
  const { data: sites } = useSuspenseQuery(sitesOptions());
  const setSelectedSite = useSessionStore((s) => s.setSelectedSite);

  const components = sites.filter((s) => !s.isPortal);
  const portal = sites.filter((s) => s.isPortal);
  const currentDown = siteIsDown(sites, siteId);
  const unreachable = `${CANNOT_REACH} ${siteShortName(siteId)}`;

  const pick = (id: string) => {
    setSelectedSite(id);
    onChange(id);
  };

  return (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Switch site"
              className="relative p-0"
            >
              <SiteIcon siteId={siteId} size={22} />
              {currentDown && (
                <AlertTriangle
                  className="absolute -right-0.5 -bottom-0.5 h-3 w-3 text-amber-500"
                  aria-label={unreachable}
                  data-testid="site-trigger-degraded"
                />
              )}
            </Button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent side="right">
          {currentDown ? unreachable : "Switch site"}
        </TooltipContent>
      </Tooltip>
      <DropdownMenuContent
        side="right"
        align="end"
        sideOffset={8}
        className="min-w-[220px]"
      >
        <DropdownMenuLabel className="text-[10px] uppercase tracking-wider text-muted-foreground">
          Component sites
        </DropdownMenuLabel>
        <DropdownMenuGroup>
          {components.map((site) => (
            <SiteMenuItem
              key={site.id}
              id={site.id}
              label={site.displayName}
              active={site.id === siteId}
              available={site.available}
              onPick={pick}
            />
          ))}
        </DropdownMenuGroup>
        {portal.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Portal
            </DropdownMenuLabel>
            <DropdownMenuGroup>
              {portal.map((site) => (
                <SiteMenuItem
                  key={site.id}
                  id={site.id}
                  label={site.displayName}
                  active={site.id === siteId}
                  available={site.available}
                  onPick={pick}
                />
              ))}
            </DropdownMenuGroup>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function SiteMenuItem({
  id,
  label,
  active,
  available,
  onPick,
}: {
  id: string;
  label: string;
  active: boolean;
  available: boolean;
  onPick: (id: string) => void;
}) {
  return (
    <DropdownMenuItem
      onSelect={() => onPick(id)}
      data-testid={`site-menu-item-${id}`}
      aria-label={available ? label : `${CANNOT_REACH} ${label}`}
      className={cn(active && "bg-primary/15 text-primary")}
    >
      <SiteIcon siteId={id} size={16} />
      <span className="flex-1 truncate">{label}</span>
      {!available && (
        <span
          className="flex items-center gap-1 text-[10px] text-amber-600"
          data-testid={`site-degraded-${id}`}
        >
          <AlertTriangle className="h-3 w-3" aria-hidden />
          {CANNOT_REACH}
        </span>
      )}
    </DropdownMenuItem>
  );
}
