"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  useMutation,
  useQuery,
  useQueryClient,
  useSuspenseQuery,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { siteShortName, type SiteResponse } from "@pathfinder/shared";
import { openStrategy } from "@pathfinder/shared/generated/hooks/useOpenStrategy";
import { listAccountStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListAccountStrategies";
import { listStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListStrategies";
import type { WdkStrategyListItem } from "@pathfinder/shared/generated/types/WdkStrategyListItem";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { toUserMessage } from "@/lib/api/errors";
import { sitesOptions } from "@/lib/api/sites";
import { chatUrl } from "@/lib/routes";
import { cn } from "@/lib/utils/cn";
import { formatSidebarTime } from "@/features/sidebar/formatTime";
import {
  readWdkStrategyEntry,
  type WdkStrategyEntry,
} from "@/features/sidebar/wdkStrategyRef";

const NOTICE_ID = "open-wdk-strategy-notice-text";

interface OpenWdkStrategyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  siteId: string;
}

function matches(item: WdkStrategyListItem, filter: string): boolean {
  const wanted = filter.trim().toLowerCase();
  return wanted === "" || item.name.toLowerCase().includes(wanted);
}

/** An example link, on the site the researcher works on. */
function exampleLink(sites: SiteResponse[], siteId: string): string {
  const here = sites.find((site) => site.id === siteId);
  if (here === undefined) return "";
  return `${here.baseUrl.replace(/\/service$/, "")}/app/workspace/strategies/214626640`;
}

/** Why an entry names nothing this site can open, or null when it does. */
function entryNotice(read: WdkStrategyEntry): string | null {
  if (read.kind !== "otherSite") return null;
  if (read.siteId === null) return `PathFinder has no site at ${read.host}.`;
  const other = siteShortName(read.siteId);
  return `That link names a ${other} strategy. Switch to ${other} to open it.`;
}

export function OpenWdkStrategyDialog({
  open,
  onOpenChange,
  siteId,
}: OpenWdkStrategyDialogProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [entry, setEntry] = useState("");
  const [filter, setFilter] = useState("");
  const { data: sites } = useSuspenseQuery(sitesOptions());
  const read = readWdkStrategyEntry(entry, siteId, sites);
  const wdkStrategyId = read.kind === "thisSite" ? read.wdkStrategyId : null;
  const notice = entryNotice(read);
  const site = siteShortName(siteId);

  const listing = useQuery({
    ...listAccountStrategiesQueryOptions(siteId),
    enabled: open && siteId !== "",
  });
  const offered = (listing.data ?? []).filter((item) => matches(item, filter));

  const importStrategy = useMutation({
    mutationFn: (id: number) => openStrategy({ siteId, wdkStrategyId: id }),
    onSuccess: async (result, id) => {
      await queryClient.invalidateQueries({
        queryKey: listStrategiesQueryOptions({ siteId }).queryKey,
      });
      setEntry("");
      setFilter("");
      onOpenChange(false);
      toast.success("Strategy opened", {
        description: `${site} strategy ${id}`,
      });
      router.push(chatUrl(siteId, result.conversationId));
    },
    onError: (error) =>
      toast.error("Could not open that strategy", {
        description: toUserMessage(error),
      }),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="open-wdk-strategy-dialog">
        <DialogHeader>
          <DialogTitle>Open a VEuPathDB strategy</DialogTitle>
          <DialogDescription>
            Pick one of your {site} strategies, or paste a strategy&apos;s link or its
            numeric id. PathFinder opens a conversation that holds it.
          </DialogDescription>
        </DialogHeader>
        <input
          type="text"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Filter your strategies..."
          aria-label="Filter your strategies"
          data-testid="open-wdk-strategy-filter"
          className="h-8 w-full rounded-md border border-input bg-transparent px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
        />
        <div className="max-h-64 overflow-auto rounded-md border border-border">
          <StrategyRows
            site={site}
            isPending={listing.isPending}
            isError={listing.isError}
            offered={offered}
            pickedId={wdkStrategyId}
            onPick={(id) => setEntry(String(id))}
          />
        </div>
        <Input
          value={entry}
          onChange={(event) => setEntry(event.target.value)}
          placeholder={exampleLink(sites, siteId)}
          aria-label="Strategy link or id"
          aria-describedby={notice === null ? undefined : NOTICE_ID}
          data-testid="open-wdk-strategy-input"
        />
        {notice !== null && (
          <p
            id={NOTICE_ID}
            className="text-sm text-destructive"
            role="status"
            data-testid="open-wdk-strategy-notice"
          >
            {notice}
          </p>
        )}
        <DialogFooter>
          <Button
            type="button"
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={importStrategy.isPending}
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={() => {
              if (wdkStrategyId !== null) importStrategy.mutate(wdkStrategyId);
            }}
            disabled={wdkStrategyId === null}
            loading={importStrategy.isPending}
            data-testid="open-wdk-strategy-confirm"
          >
            {importStrategy.isPending ? "Opening..." : "Open"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface StrategyRowsProps {
  site: string;
  isPending: boolean;
  isError: boolean;
  offered: WdkStrategyListItem[];
  pickedId: number | null;
  onPick: (wdkStrategyId: number) => void;
}

function StrategyRows({
  site,
  isPending,
  isError,
  offered,
  pickedId,
  onPick,
}: StrategyRowsProps) {
  if (isError) {
    return <RowNotice>Your {site} strategies could not be read.</RowNotice>;
  }
  if (isPending) {
    return <RowNotice>Loading your {site} strategies...</RowNotice>;
  }
  if (offered.length === 0) {
    return <RowNotice>No strategies on {site} yet.</RowNotice>;
  }
  return (
    <ul className="divide-y divide-border">
      {offered.map((item) => (
        <li key={item.wdkStrategyId}>
          <button
            type="button"
            onClick={() => onPick(item.wdkStrategyId)}
            className={cn(
              "flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left hover:bg-muted/50",
              pickedId === item.wdkStrategyId && "bg-primary/10",
            )}
            data-testid={`open-wdk-strategy-pick-${item.wdkStrategyId}`}
          >
            <span className="w-full truncate text-sm font-medium">{item.name}</span>
            <span className="text-xs text-muted-foreground">
              {resultCount(item.estimatedSize)}
              {modifiedAt(item.lastModified)}
              {item.isSaved === true ? " · Saved" : ""}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function modifiedAt(lastModified: string | undefined): string {
  const shown = lastModified == null ? "" : formatSidebarTime(lastModified);
  return shown === "" ? "" : ` · ${shown}`;
}

function resultCount(estimatedSize: number | null | undefined): string {
  if (estimatedSize == null) return "size unknown";
  return `${estimatedSize.toLocaleString()} ${estimatedSize === 1 ? "result" : "results"}`;
}

function RowNotice({ children }: { children: React.ReactNode }) {
  return <p className="p-4 text-center text-sm text-muted-foreground">{children}</p>;
}
