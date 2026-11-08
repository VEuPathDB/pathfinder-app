"use client";

import { Bookmark, CircleHelp, MessageCircle, PanelLeft, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button, buttonVariants } from "@/components/ui/button";
import { ACTIVE_PILL } from "@/lib/components/activePill";
import { chatRoot, helpUrl, savedUrl } from "@/lib/routes";
import { cn } from "@/lib/utils/cn";
import { usePhoneBarStore } from "@/state/usePhoneBarStore";
import { useLeftSidebarStore } from "@/state/useRightRailStore";

const PLACES = [
  { href: chatRoot(), icon: MessageCircle, label: "Conversation" },
  { href: savedUrl(), icon: Bookmark, label: "Saved strategies" },
];

const TAP = "size-11 shrink-0";

export function PhoneBar({ onOpenSettings }: { onOpenSettings: () => void }) {
  const pathname = usePathname();
  const collapsed = useLeftSidebarStore((s) => s.collapsed);
  const toggle = useLeftSidebarStore((s) => s.toggle);
  const setSlot = usePhoneBarStore((s) => s.setSlot);

  return (
    <nav
      aria-label="PathFinder"
      className="no-scrollbar flex h-12 shrink-0 items-center gap-0.5 overflow-x-auto border-t border-border bg-sidebar px-1"
    >
      <Button
        variant="ghost"
        size="icon"
        onClick={toggle}
        aria-label={
          collapsed ? "Open conversation sidebar" : "Collapse conversation sidebar"
        }
        aria-pressed={!collapsed}
        className={cn(TAP, !collapsed && ACTIVE_PILL)}
      >
        <PanelLeft className="h-4 w-4" aria-hidden />
      </Button>
      {PLACES.map(({ href, icon: Icon, label }) => {
        const active = pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            aria-label={label}
            aria-current={active ? "page" : undefined}
            className={cn(
              buttonVariants({ variant: "ghost", size: "icon" }),
              TAP,
              active && ACTIVE_PILL,
            )}
          >
            <Icon className="h-4 w-4" aria-hidden />
          </Link>
        );
      })}
      <div className="mx-1 h-6 w-px shrink-0 bg-border" />
      <div
        data-testid="phone-bar-slot"
        ref={setSlot}
        className="flex shrink-0 items-center gap-0.5"
      />
      <div className="mx-1 h-6 w-px shrink-0 bg-border" />
      <Link
        href={helpUrl()}
        aria-label="Help"
        className={cn(buttonVariants({ variant: "ghost", size: "icon" }), TAP)}
      >
        <CircleHelp className="h-4 w-4" aria-hidden />
      </Link>
      <Button
        variant="ghost"
        size="icon"
        onClick={() => onOpenSettings()}
        aria-label="Settings"
        className={TAP}
      >
        <Settings className="h-4 w-4" aria-hidden />
      </Button>
    </nav>
  );
}
