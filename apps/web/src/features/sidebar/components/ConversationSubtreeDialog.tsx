"use client";

import { GitBranch, Trash2 } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { ConversationItem } from "@/features/sidebar/components/conversationSidebarTypes";
import { formatSidebarTime } from "@/features/sidebar/formatTime";
import { chatUrl } from "@/lib/routes";
import { cn } from "@/lib/utils/cn";

import type { SubtreeNode } from "./ConversationSubtree";

interface FullTreeLine {
  item: ConversationItem;
  depth: number;
}

function flattenFull(nodes: readonly SubtreeNode[], depth: number): FullTreeLine[] {
  const out: FullTreeLine[] = [];
  for (const node of nodes) {
    out.push({ item: node.item, depth });
    out.push(...flattenFull(node.children, depth + 1));
  }
  return out;
}

interface Props {
  rootId: string;
  nodes: SubtreeNode[];
  activeId: string | null;
  open: boolean;
  onClose: () => void;
  onStartDelete: (item: ConversationItem) => void;
}

export function ConversationSubtreeDialog({
  rootId,
  nodes,
  activeId,
  open,
  onClose,
  onStartDelete,
}: Props) {
  const lines = flattenFull(nodes, 1);
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent
        className="flex h-[90vh] w-[90vw] max-w-none flex-col p-0 sm:max-w-none"
        data-testid={`conversation-subtree-dialog-${rootId}`}
      >
        <DialogHeader className="border-b border-border px-6 py-4">
          <DialogTitle>Conversation branches</DialogTitle>
        </DialogHeader>
        <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto p-4">
          {lines.map(({ item, depth }) => {
            const isActive = activeId === item.id;
            return (
              <li
                key={item.id}
                className="group relative"
                data-testid="subtree-dialog-item"
                data-conversation-id={item.id}
              >
                <Link
                  href={chatUrl(item.siteId, item.id)}
                  onClick={onClose}
                  className={cn(
                    "flex min-w-0 items-start gap-2 rounded px-2 py-2 pr-10 text-sm transition-colors",
                    isActive ? "bg-primary/15 text-foreground" : "hover:bg-muted/60",
                  )}
                  style={{ paddingLeft: `${0.5 + depth * 1.25}rem` }}
                >
                  <GitBranch
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground"
                    aria-hidden
                  />
                  <span className="min-w-0 flex-1 break-words">{item.title}</span>
                  <span className="ml-2 shrink-0 text-xs text-muted-foreground">
                    {formatSidebarTime(item.updatedAt)}
                  </span>
                </Link>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  aria-label="Delete branch"
                  onClick={() => onStartDelete(item)}
                  className="absolute right-2 top-2 opacity-0 transition group-hover:opacity-100 focus-visible:opacity-100 text-destructive hover:bg-destructive/10 hover:text-destructive"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </li>
            );
          })}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
