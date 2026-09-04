"use client";

import { AnimatePresence, motion } from "motion/react";

import type { ConversationItem } from "@/features/sidebar/components/conversationSidebarTypes";
import { ConversationListItem } from "@/features/sidebar/components/ConversationListItem";
import { ConversationSubtree } from "@/features/sidebar/components/ConversationSubtree";
import { toTreeRoots } from "@/features/sidebar/conversationTree";

interface ConversationListProps {
  items: ConversationItem[];
  query: string;
  hasInitiallyLoaded: boolean;
  activeId: string | null;
  renamingId: string | null;
  renameValue: string;
  onRenameValueChange: (v: string) => void;
  onCommitRename: (item: ConversationItem) => void;
  onCancelRename: () => void;
  onStartRename: (item: ConversationItem) => void;
  onStartDelete: (item: ConversationItem) => void;
  onToggleSaved: (item: ConversationItem) => void;
  onDuplicate: (item: ConversationItem) => void;
}

export function ConversationList({
  items,
  query,
  hasInitiallyLoaded,
  activeId,
  renamingId,
  renameValue,
  onRenameValueChange,
  onCommitRename,
  onCancelRename,
  onStartRename,
  onStartDelete,
  onToggleSaved,
  onDuplicate,
}: ConversationListProps) {
  const roots = toTreeRoots(items);

  return (
    <div className="-mr-1 min-h-0 flex-1 overflow-y-auto pr-1">
      {items.length === 0 && hasInitiallyLoaded && (
        <div className="py-4 text-center text-xs text-muted-foreground">
          {query.trim()
            ? "No conversations match your search."
            : "No conversations yet."}
        </div>
      )}
      <div className="space-y-1">
        <AnimatePresence initial={false}>
          {roots.map((root) => (
            <motion.div
              key={root.item.id}
              layout
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.15 }}
            >
              <ConversationListItem
                item={root.item}
                isActive={activeId === root.item.id}
                isRenaming={renamingId === root.item.id}
                renameValue={renameValue}
                onRenameValueChange={onRenameValueChange}
                onCommitRename={onCommitRename}
                onCancelRename={onCancelRename}
                onStartRename={onStartRename}
                onStartDelete={onStartDelete}
                onToggleSaved={onToggleSaved}
                onDuplicate={onDuplicate}
              />
              {root.children.length > 0 && (
                <ConversationSubtree
                  rootId={root.item.id}
                  nodes={root.children}
                  activeId={activeId}
                  onStartDelete={onStartDelete}
                />
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
