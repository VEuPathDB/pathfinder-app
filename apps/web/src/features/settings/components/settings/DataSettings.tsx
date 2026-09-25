"use client";

/** The four tiers of data clearing a user can ask for, widest last. */
import { useState } from "react";
import { toast } from "sonner";
import { siteShortName } from "@pathfinder/shared";
import { requestVoid } from "@/lib/api/http";
import { listStrategies } from "@pathfinder/shared/generated/hooks/useListStrategies";
import { deleteStrategy } from "@pathfinder/shared/generated/hooks/useDeleteStrategy";
import { purgeUserDataEndpoint } from "@pathfinder/shared/generated/hooks/usePurgeUserDataEndpoint";
import type { PurgeCounts } from "@pathfinder/shared/generated/types/PurgeCounts";
import { useAsyncAction } from "@/features/settings/asyncAction";
import { Loader2, Trash2, AlertTriangle } from "lucide-react";
import { Input } from "@/components/ui/input";

interface DataSettingsProps {
  siteId: string;
}

/** How long the outcome stays on screen before the page reloads. */
const NOTICE_BEFORE_RELOAD_MS = 4000;

function reportPurge(deleted: PurgeCounts): void {
  const done = `VEuPathDB strategies deleted: ${String(deleted.wdkStrategies)}.`;
  const memories = `Memories deleted: ${String(deleted.memories)}.`;
  if (deleted.wdkStrategiesKept > 0) {
    toast.error("Not everything was deleted", {
      description: `${done} Could not delete: ${String(
        deleted.wdkStrategiesKept,
      )}. The conversations and runs that used them were kept, so you can try again. ${memories}`,
    });
    return;
  }
  toast.success("Data cleared", { description: `${done} ${memories}` });
}

export function DataSettings({ siteId }: DataSettingsProps) {
  const [clearing, setClearing] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<string | null>(null);
  const [wdkConfirmText, setWdkConfirmText] = useState("");
  const { run, error } = useAsyncAction();
  const siteName = siteShortName(siteId);

  const clearStrategies = async () => {
    setClearing("strategies");
    await run(async () => {
      const all = await listStrategies({ siteId });
      await Promise.allSettled(all.map((s) => deleteStrategy(s.id)));
      window.location.reload();
    });
    setClearing(null);
    setConfirmAction(null);
  };

  const clearSiteData = async () => {
    setClearing("site");
    await run(async () => {
      await requestVoid("/api/v1/user/data", {
        method: "DELETE",
        query: { siteId, deleteWdk: "false" },
      });
      window.location.reload();
    });
    setClearing(null);
    setConfirmAction(null);
  };

  const clearAllLocal = async () => {
    setClearing("all-local");
    await run(async () => {
      await requestVoid("/api/v1/user/data", {
        method: "DELETE",
        query: { deleteWdk: "false" },
      });
      window.location.reload();
    });
    setClearing(null);
    setConfirmAction(null);
  };

  const clearAllWithWdk = async () => {
    setClearing("all-wdk");
    await run(async () => {
      const result = await purgeUserDataEndpoint({ deleteWdk: true });
      reportPurge(result.deleted);
      window.setTimeout(() => {
        window.location.reload();
      }, NOTICE_BEFORE_RELOAD_MS);
    });
    setClearing(null);
    setConfirmAction(null);
    setWdkConfirmText("");
  };

  return (
    <div className="space-y-4">
      {error != null && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <DangerAction
        label="Clear strategies"
        description={`Remove every conversation for ${siteName} from PathFinder. A conversation linked to a VEuPathDB strategy moves to Recently deleted instead, and the strategy itself stays. Gene sets, runs and control sets are untouched.`}
        loading={clearing === "strategies"}
        confirmed={confirmAction === "strategies"}
        onConfirm={() => setConfirmAction("strategies")}
        onExecute={() => {
          void clearStrategies();
        }}
        onCancel={() => setConfirmAction(null)}
      />

      <DangerAction
        label="Clear site data"
        description={`Delete the gene sets, runs and control sets for ${siteName}, and move every conversation on it to Recently deleted. The investigations from ${siteName} still waiting for review go with them. A conversation in Recently deleted can be restored from the sidebar. VEuPathDB strategies and your memories stay.`}
        loading={clearing === "site"}
        confirmed={confirmAction === "site"}
        onConfirm={() => setConfirmAction("site")}
        onExecute={() => {
          void clearSiteData();
        }}
        onCancel={() => setConfirmAction(null)}
      />

      <DangerAction
        label="Clear ALL data"
        description="Delete the gene sets, runs and control sets on every site, and your memories with them. The investigations still waiting for review go too. Every conversation moves to Recently deleted, and can be restored from the sidebar. VEuPathDB strategies are kept but hidden from sync. Your monthly spend counter and exports stay."
        loading={clearing === "all-local"}
        confirmed={confirmAction === "all-local"}
        onConfirm={() => setConfirmAction("all-local")}
        onExecute={() => {
          void clearAllLocal();
        }}
        onCancel={() => setConfirmAction(null)}
      />

      {/* Clear ALL data + WDK - requires typing "delete my data" */}
      <div className="rounded-md border border-destructive/30 px-3 py-2.5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-medium text-foreground">
              Clear ALL data + VEuPathDB
            </div>
            <div
              data-testid="wdk-purge-description"
              className="text-xs text-muted-foreground"
            >
              Delete everything locally, memories and the investigations still waiting
              for review included, <strong>and</strong> the strategies PathFinder
              created in VEuPathDB. A conversation or a run whose strategy the site
              keeps is kept too, so you can try again. Your monthly spend counter and
              exports stay. This cannot be undone.
            </div>
          </div>
          {confirmAction === "all-wdk" ? (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setConfirmAction(null);
                  setWdkConfirmText("");
                }}
                disabled={clearing === "all-wdk"}
                className="rounded-md border border-border px-2 py-1 text-xs font-medium text-muted-foreground transition hover:bg-muted disabled:opacity-60"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  void clearAllWithWdk();
                }}
                disabled={
                  clearing === "all-wdk" ||
                  wdkConfirmText.trim().toLowerCase() !== "delete my data"
                }
                className="inline-flex items-center gap-1 rounded-md bg-destructive px-2 py-1 text-xs font-medium text-destructive-foreground transition hover:bg-destructive/90 disabled:opacity-60"
              >
                {clearing === "all-wdk" && <Loader2 className="h-3 w-3 animate-spin" />}
                Confirm
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmAction("all-wdk")}
              className="inline-flex items-center gap-1 rounded-md border border-destructive/30 px-2 py-1 text-xs font-medium text-destructive transition hover:bg-destructive/5"
            >
              <Trash2 className="h-3 w-3" />
              Clear ALL + VEuPathDB
            </button>
          )}
        </div>

        {confirmAction === "all-wdk" && (
          <div className="mt-3 rounded-md border border-destructive/20 bg-destructive/5 p-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
              <div className="space-y-2">
                <p className="text-xs font-medium text-destructive">
                  This permanently deletes the strategies PathFinder created in your
                  VEuPathDB account, on every site. Strategies you made in VEuPathDB
                  yourself are kept.
                </p>
                <p className="text-xs text-muted-foreground">
                  Type{" "}
                  <span className="font-mono font-semibold text-foreground">
                    delete my data
                  </span>{" "}
                  to confirm:
                </p>
                <Input
                  type="text"
                  value={wdkConfirmText}
                  onChange={(e) => setWdkConfirmText(e.target.value)}
                  placeholder="delete my data"
                  className="bg-background px-2 py-1 placeholder:text-muted-foreground"
                  autoFocus
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// --- DangerAction (internal to DataSettings) ---

function DangerAction({
  label,
  description,
  loading,
  confirmed,
  onConfirm,
  onExecute,
  onCancel,
}: {
  label: string;
  description: string;
  loading: boolean;
  confirmed: boolean;
  onConfirm: () => void;
  onExecute: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2.5">
      <div>
        <div className="text-sm font-medium text-foreground">{label}</div>
        <div className="text-xs text-muted-foreground">{description}</div>
      </div>
      {confirmed ? (
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="rounded-md border border-border px-2 py-1 text-xs font-medium text-muted-foreground transition hover:bg-muted disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onExecute}
            disabled={loading}
            className="inline-flex items-center gap-1 rounded-md bg-destructive px-2 py-1 text-xs font-medium text-destructive-foreground transition hover:bg-destructive/90 disabled:opacity-60"
          >
            {loading && <Loader2 className="h-3 w-3 animate-spin" />}
            Confirm
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={onConfirm}
          className="inline-flex items-center gap-1 rounded-md border border-destructive/30 px-2 py-1 text-xs font-medium text-destructive transition hover:bg-destructive/5"
        >
          <Trash2 className="h-3 w-3" />
          {label}
        </button>
      )}
    </div>
  );
}
