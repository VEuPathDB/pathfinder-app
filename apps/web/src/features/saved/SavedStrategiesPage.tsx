"use client";

import { siteShortName } from "@pathfinder/shared";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  queryOptions,
  useMutation,
  useQueryClient,
  useSuspenseQuery,
} from "@tanstack/react-query";
import { Bookmark, ExternalLink, MessageSquarePlus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { client } from "@/lib/api/client";
import { insertSavedStrategy } from "@/lib/api/conversations";
import type { ConversationResponse } from "@pathfinder/shared/generated/types/ConversationResponse";
import { listStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListStrategies";
import { beginStrategy } from "@pathfinder/shared/generated/hooks/useBeginStrategy";
import { deleteStrategy } from "@pathfinder/shared/generated/hooks/useDeleteStrategy";
import { toUserMessage } from "@/lib/api/errors";
import { QueryBoundary } from "@/lib/components/QueryBoundary";
import { chatRoot, chatUrl } from "@/lib/routes";
import { useRightRailStore } from "@/state/useRightRailStore";

interface SavedStrategiesPageProps {
  siteId: string;
}

export function SavedStrategiesPage({ siteId }: SavedStrategiesPageProps) {
  return (
    <QueryBoundary>
      <SavedStrategiesPageInner siteId={siteId} />
    </QueryBoundary>
  );
}

function consumerCountsOptions(siteId: string) {
  return queryOptions({
    queryKey: ["saved-strategy-consumers", siteId] as const,
    queryFn: async () => {
      const resp = await client<{ counts: Record<string, number> }>({
        method: "get",
        url: `/api/v1/conversations/saved-strategy-consumers`,
        params: { siteId },
      });
      // Pydantic camelCase serializes int keys as strings - coerce.
      const out: Record<number, number> = {};
      for (const [k, v] of Object.entries(resp.data.counts)) {
        const id = Number(k);
        if (Number.isFinite(id)) out[id] = v;
      }
      return out;
    },
  });
}

function SavedStrategiesPageInner({ siteId }: SavedStrategiesPageProps) {
  const { data: all } = useSuspenseQuery(listStrategiesQueryOptions({ siteId }));
  const { data: counts } = useSuspenseQuery(consumerCountsOptions(siteId));
  const saved = all.filter((c) => c.isSaved === true);
  const [filter, setFilter] = useState("");
  const filtered =
    filter.trim() === ""
      ? saved
      : saved.filter((c) => c.name.toLowerCase().includes(filter.trim().toLowerCase()));

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="border-b border-border px-6 py-4">
        <div className="flex items-center gap-3">
          <Bookmark className="h-5 w-5 shrink-0 text-primary" aria-hidden />
          <h1 className="text-lg font-semibold">Saved strategies</h1>
          <div className="flex-1" />
          <Input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter by name..."
            className="h-8 w-64 shrink-0"
            data-testid="saved-strategies-filter"
          />
        </div>
        <p className="mt-1 pl-8 text-xs text-muted-foreground">
          Reusable strategies you can insert into any conversation as a collapsed input.
        </p>
      </header>
      <div className="min-h-0 flex-1 overflow-auto px-6 py-4">
        {filtered.length === 0 ? (
          <EmptyState hasAny={saved.length > 0} siteId={siteId} />
        ) : (
          <ul
            className="divide-y divide-border rounded-md border border-border"
            data-testid="saved-strategies-list"
          >
            {filtered.map((conv) => (
              <SavedRow
                key={conv.id}
                conv={conv}
                siteId={siteId}
                consumerCount={
                  conv.wdkStrategyId != null ? (counts[conv.wdkStrategyId] ?? 0) : 0
                }
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function EmptyState({ hasAny, siteId }: { hasAny: boolean; siteId: string }) {
  if (hasAny) {
    return (
      <div className="rounded border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
        No matches.
      </div>
    );
  }
  return (
    <div className="rounded border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
      <p>No saved strategies yet.</p>
      <p className="mt-2">
        Open a strategy step and choose{" "}
        <span className="font-medium">Save as reusable</span> to add one here, or{" "}
        <Link
          className="text-primary underline-offset-2 hover:underline"
          href={chatRoot(siteId)}
        >
          start a new chat
        </Link>{" "}
        to build one.
      </p>
    </div>
  );
}

/** The reason an insert failed, plus the fate of the chat it opened for it. */
async function discarded(conversationId: string, reason: string): Promise<string> {
  try {
    await deleteStrategy(conversationId);
    return `${reason} The empty chat it opened was removed.`;
  } catch {
    return `${reason} The empty chat it opened is still in the sidebar.`;
  }
}

function SavedRow({
  conv,
  siteId,
  consumerCount,
}: {
  conv: ConversationResponse;
  siteId: string;
  consumerCount: number;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const openRailPanel = useRightRailStore((s) => s.openPanelId);
  const del = useMutation({
    mutationFn: () => deleteStrategy(conv.id, { deleteFromWdk: true, cascade: true }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["conversations", "list", siteId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["saved-strategy-consumers", siteId],
      });
      toast.success("Saved strategy deleted", { description: conv.name });
    },
    onError: (error) => {
      toast.error("Delete failed", { description: toUserMessage(error) });
    },
  });

  const useInNewChat = useMutation({
    mutationFn: async () => {
      const conversationId = crypto.randomUUID();
      await beginStrategy(conversationId, { siteId, seedText: conv.name });
      try {
        await insertSavedStrategy({
          conversationId,
          siteId,
          targetStepId: "",
          savedWdkStrategyId: conv.wdkStrategyId ?? 0,
        });
      } catch (error) {
        throw new Error(await discarded(conversationId, toUserMessage(error)));
      }
      return conversationId;
    },
    onSuccess: (conversationId) => {
      void queryClient.invalidateQueries({
        queryKey: ["conversations", "list", siteId],
      });
      // The new thread has no messages yet, so the strategy panel is the only
      // place the inserted steps are visible on arrival.
      openRailPanel(conversationId, "strategy", {});
      toast.success("Inserted into a new chat", { description: conv.name });
      router.push(chatUrl(siteId, conversationId));
    },
    onError: (error) => {
      void queryClient.invalidateQueries({
        queryKey: ["conversations", "list", siteId],
      });
      toast.error(`Could not use "${conv.name}" in a new chat`, {
        description: toUserMessage(error),
      });
    },
  });

  const open = (): void => {
    router.push(chatUrl(siteId, conv.id));
  };

  const stepCount = conv.stepCount ?? conv.steps?.length ?? 0;
  const size = conv.estimatedSize ?? null;

  return (
    <li
      className="flex items-center gap-3 px-4 py-3 hover:bg-muted/40"
      data-testid={`saved-strategy-${conv.id}`}
    >
      <button
        type="button"
        onClick={open}
        className="flex flex-1 flex-col items-start gap-0.5 text-left"
      >
        <span className="text-sm font-medium">{conv.name}</span>
        <span className="text-xs text-muted-foreground">
          {stepCount} {stepCount === 1 ? "step" : "steps"}
          {size != null ? ` · ${size.toLocaleString()} results` : ""}
          {conv.recordType != null ? ` · ${conv.recordType}` : ""}
        </span>
      </button>
      {consumerCount > 0 && (
        <span
          className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-primary"
          title={`${consumerCount} other conversation(s) import this saved strategy`}
        >
          {consumerCount} consumer{consumerCount === 1 ? "" : "s"}
        </span>
      )}
      {conv.wdkStrategyId != null && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="gap-1 text-xs"
          onClick={() => useInNewChat.mutate()}
          loading={useInNewChat.isPending}
          data-testid={`saved-strategy-use-${conv.id}`}
        >
          {!useInNewChat.isPending && (
            <MessageSquarePlus className="h-4 w-4" aria-hidden />
          )}
          {useInNewChat.isPending ? "Inserting..." : "Use in new chat"}
        </Button>
      )}
      {conv.wdkUrl != null && conv.wdkUrl !== "" && (
        <Button asChild variant="ghost" size="sm">
          <a
            href={conv.wdkUrl}
            target="_blank"
            rel="noreferrer"
            aria-label={`Open in ${siteShortName(siteId)}`}
          >
            <ExternalLink className="h-4 w-4" aria-hidden />
          </a>
        </Button>
      )}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => del.mutate()}
        disabled={del.isPending}
        aria-label="Delete saved strategy"
        data-testid={`saved-strategy-delete-${conv.id}`}
      >
        <Trash2 className="h-4 w-4" aria-hidden />
      </Button>
    </li>
  );
}
