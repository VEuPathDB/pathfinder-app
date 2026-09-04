"use client";

import { GitBranch, MoreVertical } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { ConversationItem } from "@/features/sidebar/components/conversationSidebarTypes";
import { formatSidebarTime } from "@/features/sidebar/formatTime";
import { chatUrl } from "@/lib/routes";
import { cn } from "@/lib/utils/cn";

import { ConversationSubtreeDialog } from "./ConversationSubtreeDialog";

const MAX_INLINE_DEPTH = 2;
const MAX_INLINE_NODES = 6;

export interface SubtreeNode {
  item: ConversationItem;
  children: SubtreeNode[];
}

function flattenCapped(
  roots: readonly SubtreeNode[],
  depth = 1,
): {
  visible: { item: ConversationItem; depth: number }[];
  truncated: boolean;
  total: number;
} {
  const out: { item: ConversationItem; depth: number }[] = [];
  let truncated = false;
  let total = 0;
  const walk = (node: SubtreeNode, d: number) => {
    total += 1;
    if (out.length >= MAX_INLINE_NODES) {
      truncated = true;
      return;
    }
    if (d > MAX_INLINE_DEPTH) {
      truncated = true;
      return;
    }
    out.push({ item: node.item, depth: d });
    for (const c of node.children) walk(c, d + 1);
  };
  for (const r of roots) walk(r, depth);
  return { visible: out, truncated, total };
}

interface ConversationSubtreeProps {
  rootId: string;
  nodes: SubtreeNode[];
  activeId: string | null;
  onStartDelete: (item: ConversationItem) => void;
}

export function ConversationSubtree({
  rootId,
  nodes,
  activeId,
  onStartDelete,
}: ConversationSubtreeProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const { visible, truncated, total } = flattenCapped(nodes);

  if (visible.length === 0) return null;

  return (
    <>
      <ul className="mt-1 ml-2.5 space-y-0.5 border-l border-border/60 pl-2">
        {visible.map(({ item, depth }) => {
          const isActive = activeId === item.id;
          return (
            <li
              key={item.id}
              className="group relative"
              data-testid="subtree-item"
              data-conversation-id={item.id}
            >
              <Link
                href={chatUrl(item.siteId, item.id)}
                className={cn(
                  "flex items-center gap-1.5 rounded py-0.5 pr-6 text-[11px] transition-colors",
                  isActive
                    ? "bg-primary/15 text-foreground"
                    : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                )}
                style={{ paddingLeft: `${0.375 + (depth - 1) * 0.75}rem` }}
              >
                <GitBranch className="h-3 w-3 shrink-0" aria-hidden />
                <span className="truncate">{item.title}</span>
                <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">
                  {formatSidebarTime(item.updatedAt)}
                </span>
              </Link>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    aria-label="Branch actions"
                    className="absolute right-0 top-0 rounded p-0.5 text-muted-foreground opacity-0 transition hover:bg-muted hover:text-foreground group-hover:opacity-100 focus-visible:opacity-100 aria-expanded:opacity-100"
                  >
                    <MoreVertical className="h-3 w-3" aria-hidden />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" sideOffset={2}>
                  <DropdownMenuItem
                    variant="destructive"
                    onSelect={() => onStartDelete(item)}
                  >
                    Delete branch
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </li>
          );
        })}
        {truncated && (
          <li>
            <button
              type="button"
              onClick={() => setDialogOpen(true)}
              className="flex w-full items-center gap-1.5 rounded px-1.5 py-0.5 text-left text-[11px] text-muted-foreground hover:bg-muted/50 hover:text-primary"
            >
              <GitBranch className="h-3 w-3 shrink-0" aria-hidden />
              <span>See full tree ({total})</span>
            </button>
          </li>
        )}
      </ul>

      <ConversationSubtreeDialog
        rootId={rootId}
        nodes={nodes}
        activeId={activeId}
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onStartDelete={(item) => {
          setDialogOpen(false);
          onStartDelete(item);
        }}
      />
    </>
  );
}
