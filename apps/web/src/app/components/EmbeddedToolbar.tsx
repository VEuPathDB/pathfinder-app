"use client";

import { Layers, MessageCircle, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { chatRoot, workbenchRoot } from "@/lib/routes";

interface EmbeddedToolbarProps {
  siteId: string;
  onOpenSettings: () => void;
}

export function EmbeddedToolbar({ siteId, onOpenSettings }: EmbeddedToolbarProps) {
  const pathname = usePathname();
  const chatActive = pathname.startsWith(chatRoot(siteId));
  const workbenchActive = pathname.startsWith(workbenchRoot(siteId));

  return (
    <div className="flex items-center justify-end gap-1 border-b border-border bg-background px-3 py-1">
      <Link
        href={chatRoot(siteId)}
        aria-label="Go to Chat"
        aria-current={chatActive ? "page" : undefined}
        className={
          chatActive
            ? "inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground"
            : "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium text-muted-foreground transition-all duration-150 hover:bg-accent hover:text-accent-foreground"
        }
      >
        <MessageCircle className="h-3.5 w-3.5" aria-hidden />
        Chat
      </Link>
      <Link
        href={workbenchRoot(siteId)}
        aria-label="Go to Workbench"
        aria-current={workbenchActive ? "page" : undefined}
        className={
          workbenchActive
            ? "inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground"
            : "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium text-muted-foreground transition-all duration-150 hover:bg-accent hover:text-accent-foreground"
        }
      >
        <Layers className="h-3.5 w-3.5" aria-hidden />
        Workbench
      </Link>
      <div className="mx-1 h-4 w-px bg-border" />
      <Button
        variant="ghost"
        size="icon"
        onClick={onOpenSettings}
        aria-label="Settings"
        className="h-7 w-7"
      >
        <Settings className="h-3.5 w-3.5" aria-hidden />
      </Button>
    </div>
  );
}
