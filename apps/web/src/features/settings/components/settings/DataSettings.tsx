"use client";

/**
 * DataSettings -- destructive data-clearing actions.
 *
 * Four tiers:
 * - Clear strategies (current site only)
 * - Clear site data (strategies + gene sets + Redis for current site)
 * - Clear ALL data (everything locally, remote strategies dismissed to prevent re-sync)
 * - Clear ALL data + VEuPathDB (everything locally + delete remotely, requires "delete my data")
 */

import { useState } from "react";
import { requestVoid } from "@/lib/api/http";
import { listStrategies } from "@pathfinder/shared/generated/hooks/useListStrategies";
import { deleteStrategy } from "@pathfinder/shared/generated/hooks/useDeleteStrategy";
import { useAsyncAction } from "@/features/settings/asyncAction";
import { Loader2, Trash2, AlertTriangle } from "lucide-react";
import { Input } from "@/components/ui/input";

interface DataSettingsProps {
  siteId: string;
}

export function DataSettings({ siteId }: DataSettingsProps) {
  const [clearing, setClearing] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<string | null>(null);
  const [wdkConfirmText, setWdkConfirmText] = useState("");
  const { run, error } = useAsyncAction();

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
      await requestVoid("/api/v1/user/data", {
        method: "DELETE",
        query: { deleteWdk: "true" },
      });
      window.location.reload();
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
        description="Delete all draft strategies for the current site."
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
        description={`Delete all strategies, gene sets, and chat history for ${siteId}.`}
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
        description="Delete everything locally. VEuPathDB strategies are kept but hidden from sync."
        loading={clearing === "all-local"}
        confirmed={confirmAction === "all-local"}
        onConfirm={() => setConfirmAction("all-local")}
        onExecute={() => {
          void clearAllLocal();
        }}
        onCancel={() => setConfirmAction(null)}
      />

      {/* Clear ALL data + WDK — requires typing "delete my data" */}
      <div className="rounded-md border border-destructive/30 px-3 py-2.5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-medium text-foreground">
              Clear ALL data + VEuPathDB
            </div>
            <div className="text-xs text-muted-foreground">
              Delete everything locally <strong>and</strong> from VEuPathDB. This cannot
              be undone.
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
                  This will permanently delete all strategies from VEuPathDB across all
                  sites.
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
