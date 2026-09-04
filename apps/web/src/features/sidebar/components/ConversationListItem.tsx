import { MoreVertical } from "lucide-react";
import Link from "next/link";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { ConversationItem } from "@/features/sidebar/components/conversationSidebarTypes";
import { useFlushBeforeNav } from "@/features/strategy/hooks/useFlushBeforeNav";
import { formatSidebarTime } from "@/features/sidebar/formatTime";
import { chatUrl } from "@/lib/routes";
import { cn } from "@/lib/utils/cn";

interface ConversationListItemProps {
  item: ConversationItem;
  isActive: boolean;
  isRenaming: boolean;
  renameValue: string;
  onRenameValueChange: (value: string) => void;
  onCommitRename: (item: ConversationItem) => void;
  onCancelRename: () => void;
  onStartRename: (item: ConversationItem) => void;
  onStartDelete: (item: ConversationItem) => void;
  onToggleSaved: (item: ConversationItem) => void;
  onDuplicate?: (item: ConversationItem) => void;
}

export function ConversationListItem({
  item,
  isActive,
  isRenaming,
  renameValue,
  onRenameValueChange,
  onCommitRename,
  onCancelRename,
  onStartRename,
  onStartDelete,
  onToggleSaved,
  onDuplicate,
}: ConversationListItemProps) {
  const { navigate } = useFlushBeforeNav();
  const metaParts: string[] = [];
  if (item.stepCount > 0) {
    metaParts.push(`${item.stepCount} step${item.stepCount === 1 ? "" : "s"}`);
  }
  metaParts.push(formatSidebarTime(item.updatedAt));

  return (
    <div
      data-testid="conversation-item"
      data-conversation-id={item.id}
      className={cn(
        "group relative rounded-md px-2.5 py-1.5 transition-colors",
        // The primary tint marks the active row; its text stays on a dark
        // foreground tone, which the primary tone cannot reach over that tint.
        isActive
          ? "bg-primary/15 text-foreground hover:bg-primary/20"
          : "text-foreground/85 hover:bg-muted/60",
      )}
    >
      {isRenaming ? (
        <Input
          data-testid="conversation-rename-input"
          value={renameValue}
          onChange={(e) => onRenameValueChange(e.target.value)}
          onBlur={() => onCommitRename(item)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              onCommitRename(item);
            }
            if (e.key === "Escape") onCancelRename();
          }}
          className="h-7 min-w-0 bg-card px-1.5 py-0.5 font-medium"
          autoFocus
        />
      ) : (
        <>
          <Link
            href={chatUrl(item.siteId, item.id)}
            className="block"
            onClick={(e) => {
              if (isActive) return;
              if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
              if (e.button !== 0) return;
              e.preventDefault();
              void navigate(chatUrl(item.siteId, item.id));
            }}
          >
            <div className="truncate pr-6 text-sm font-medium" title={item.title}>
              {item.title}
            </div>
            <div
              className={cn(
                "mt-0.5 truncate text-xs",
                isActive ? "text-foreground/70" : "text-muted-foreground",
              )}
            >
              {metaParts.join(" · ")}
            </div>
          </Link>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                aria-label="Conversation actions"
                className="absolute right-1 top-1 opacity-0 transition group-hover:opacity-100 focus-visible:opacity-100 aria-expanded:opacity-100"
              >
                <MoreVertical className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" sideOffset={4} className="min-w-[160px]">
              <DropdownMenuItem onSelect={() => onStartRename(item)}>
                Rename
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => onToggleSaved(item)}>
                {item.isSaved ? "Unmark saved" : "Mark as saved"}
              </DropdownMenuItem>
              {onDuplicate != null && (
                <DropdownMenuItem onSelect={() => onDuplicate(item)}>
                  Duplicate
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                variant="destructive"
                onSelect={() => onStartDelete(item)}
              >
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </>
      )}
    </div>
  );
}
