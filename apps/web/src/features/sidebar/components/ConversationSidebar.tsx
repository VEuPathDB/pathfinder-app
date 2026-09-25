"use client";

import { useState } from "react";
import {
  AlertTriangle,
  Archive,
  ChevronDown,
  RefreshCw,
  RotateCcw,
  SquarePen,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { ASSISTANT_CHOICES } from "@/lib/assistants";
import { useConversationSidebarData } from "@/features/sidebar/hooks/useConversationSidebarData";
import { useConversationSidebarActions } from "@/features/sidebar/hooks/useConversationSidebarActions";
import { ConversationList } from "@/features/sidebar/components/ConversationList";
import { DeleteConversationModal } from "@/features/sidebar/components/DeleteConversationModal";
import { OpenWdkStrategyDialog } from "@/features/sidebar/components/OpenWdkStrategyDialog";

interface ConversationSidebarProps {
  siteId: string;
}

export function ConversationSidebar({ siteId }: ConversationSidebarProps) {
  const reportError = (message: string) => toast.error(message);

  const [showDismissed, setShowDismissed] = useState(false);
  const [showOpenWdkStrategy, setShowOpenWdkStrategy] = useState(false);

  const data = useConversationSidebarData({ siteId });
  const actions = useConversationSidebarActions({
    siteId,
    reportError,
  });

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 px-2 py-3">
      <div className="flex items-center gap-1 px-1">
        <div className="flex-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Conversations
        </div>
        <Button
          data-testid="conversations-refresh-button"
          type="button"
          variant="ghost"
          size="icon-sm"
          disabled={data.isSyncing}
          onClick={() => void data.handleManualRefresh()}
          aria-label="Refresh conversations"
          title="Refresh conversations & strategies"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${data.isSyncing ? "animate-spin" : ""}`}
          />
        </Button>
        <Button
          data-testid="conversations-new-button"
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={() => void actions.handleNewConversation()}
          aria-label="New conversation"
          title="New conversation"
        >
          <SquarePen className="h-4 w-4" />
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              data-testid="conversations-new-assistant-button"
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="Choose an assistant"
              title="Choose an assistant"
            >
              <ChevronDown className="h-3.5 w-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[220px]">
            <DropdownMenuLabel className="text-[10px] uppercase tracking-wider text-muted-foreground">
              New conversation with
            </DropdownMenuLabel>
            {ASSISTANT_CHOICES.map((choice) => (
              <DropdownMenuItem
                key={choice.id}
                data-testid={`new-chat-assistant-${choice.id}`}
                onSelect={() => void actions.handleNewConversation(choice.id)}
              >
                {choice.label}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              data-testid="open-wdk-strategy-menu-item"
              onSelect={() => setShowOpenWdkStrategy(true)}
            >
              Open a VEuPathDB strategy...
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <Input
        data-testid="conversations-search-input"
        value={data.query}
        onChange={(e) => data.setQuery(e.target.value)}
        placeholder="Search conversations..."
        aria-label="Search conversations"
        className="h-8 border-transparent bg-muted/40 text-sm shadow-none focus-visible:border-input focus-visible:bg-background"
      />

      {(!data.hasInitiallyLoaded || data.isSyncing) && data.filtered.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-2 py-10 text-muted-foreground animate-fade-in">
          <Spinner className="h-5 w-5" />
          <p className="text-xs">Loading conversations...</p>
        </div>
      )}

      <ConversationList
        items={data.filtered}
        query={data.query}
        hasInitiallyLoaded={data.hasInitiallyLoaded}
        activeId={actions.activeId}
        renamingId={actions.renamingId}
        renameValue={actions.renameValue}
        onRenameValueChange={actions.setRenameValue}
        onCommitRename={(target) => void actions.commitRename(target)}
        onCancelRename={actions.cancelRename}
        onStartRename={actions.startRename}
        onStartDelete={actions.setDeleteTarget}
        onToggleSaved={(item) => void actions.handleToggleSaved(item)}
        onDuplicate={(item) => void actions.handleDuplicate(item)}
      />

      {data.dismissedConversations.length > 0 && (
        <div className="border-t border-border pt-2">
          <Button
            data-testid="dismissed-toggle"
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setShowDismissed((prev) => !prev)}
            className="h-7 w-full justify-start gap-1.5 px-1.5 text-[11px] font-normal uppercase tracking-wider text-muted-foreground"
          >
            <Archive className="h-3 w-3" />
            <span>Recently deleted ({data.dismissedConversations.length})</span>
            <span className="ml-auto text-[10px]">
              {showDismissed ? "\u25BC" : "\u25B6"}
            </span>
          </Button>
          {showDismissed && (
            <div className="mt-1 space-y-0.5">
              {data.dismissedConversations.map((item) => (
                <div
                  key={item.id}
                  data-testid="dismissed-item"
                  data-conversation-id={item.id}
                  className="group relative rounded-md px-2.5 py-1.5 text-xs text-muted-foreground opacity-80 hover:bg-muted/40"
                >
                  <div className="truncate pr-14 text-sm">{item.title}</div>
                  <div className="absolute right-1 top-1/2 flex -translate-y-1/2 items-center gap-0.5 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
                    <Button
                      data-testid="dismissed-restore-button"
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      onClick={() => void actions.handleRestore(item.id)}
                      aria-label="Restore conversation"
                      title="Restore"
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      data-testid="dismissed-delete-button"
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      onClick={() => actions.setPermanentDeleteTarget(item.id)}
                      aria-label="Delete permanently"
                      title="Delete permanently"
                      className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <OpenWdkStrategyDialog
        open={showOpenWdkStrategy}
        onOpenChange={setShowOpenWdkStrategy}
        siteId={siteId}
      />

      <DeleteConversationModal
        target={actions.deleteTarget}
        isDeleting={actions.isDeleting}
        onClose={() => actions.setDeleteTarget(null)}
        onConfirmDelete={(opts) => void actions.confirmDelete(opts)}
      />

      <Dialog
        open={actions.permanentDeleteTarget !== null}
        onOpenChange={(open) => !open && actions.setPermanentDeleteTarget(null)}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Permanently delete conversation</DialogTitle>
            <DialogDescription className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
              <span>
                This permanently removes the conversation and all its messages. This
                cannot be undone.
              </span>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => actions.setPermanentDeleteTarget(null)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() => void actions.confirmPermanentDelete()}
            >
              Delete permanently
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
