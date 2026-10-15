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
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { SettingsRow, SettingsSection } from "./SettingsRow";

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

  const wdkArmed = confirmAction === "all-wdk";
  const wdkPhraseTyped = wdkConfirmText.trim().toLowerCase() === "delete my data";

  return (
    <div className="space-y-4">
      {error != null && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <SettingsSection
        title="Clear data"
        description="A conversation in Recently deleted can be restored from the sidebar."
      >
        <DangerAction
          label="Clear strategies"
          description={`Remove the ${siteName} conversations. One linked to a VEuPathDB strategy moves to Recently deleted, and the strategy stays.`}
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
          description={`Delete the ${siteName} gene sets, runs, control sets and copies waiting for review. Conversations move to Recently deleted. Strategies and memories stay.`}
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
          description="Delete the gene sets, runs, control sets, memories and copies waiting for review on every site. Conversations move to Recently deleted. Strategies stay but stop syncing."
          loading={clearing === "all-local"}
          confirmed={confirmAction === "all-local"}
          onConfirm={() => setConfirmAction("all-local")}
          onExecute={() => {
            void clearAllLocal();
          }}
          onCancel={() => setConfirmAction(null)}
        />
        <div>
          <SettingsRow
            label="Clear ALL data + VEuPathDB"
            hint={
              <span data-testid="wdk-purge-description">
                Everything above, plus the strategies PathFinder created in VEuPathDB.
                This cannot be undone.
              </span>
            }
          >
            {wdkArmed ? (
              <ConfirmButtons
                loading={clearing === "all-wdk"}
                ready={wdkPhraseTyped}
                onCancel={() => {
                  setConfirmAction(null);
                  setWdkConfirmText("");
                }}
                onExecute={() => {
                  void clearAllWithWdk();
                }}
              />
            ) : (
              <ClearButton
                name="Clear ALL + VEuPathDB"
                onClick={() => setConfirmAction("all-wdk")}
              />
            )}
          </SettingsRow>
          {wdkArmed && (
            <div className="mb-3 space-y-2 rounded-md border border-destructive/20 bg-destructive/5 p-3">
              <p className="flex items-start gap-2 text-xs font-medium text-destructive">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                This permanently deletes the strategies PathFinder created in your
                VEuPathDB account, on every site. Strategies you made in VEuPathDB
                yourself are kept.
              </p>
              <Input
                type="text"
                value={wdkConfirmText}
                onChange={(e) => setWdkConfirmText(e.target.value)}
                placeholder="delete my data"
                aria-label="Type delete my data to confirm"
                className="h-8 bg-background text-sm"
                autoFocus
              />
            </div>
          )}
        </div>
      </SettingsSection>
    </div>
  );
}

function ClearButton({ name, onClick }: { name: string; onClick: () => void }) {
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      aria-label={name}
      onClick={onClick}
      className="border-destructive/30 text-destructive hover:bg-destructive/5 hover:text-destructive"
    >
      <Trash2 className="h-3.5 w-3.5" />
      Clear
    </Button>
  );
}

function ConfirmButtons({
  loading,
  ready,
  onCancel,
  onExecute,
}: {
  loading: boolean;
  ready: boolean;
  onCancel: () => void;
  onExecute: () => void;
}) {
  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onCancel}
        disabled={loading}
      >
        Cancel
      </Button>
      <Button
        type="button"
        variant="destructive"
        size="sm"
        onClick={onExecute}
        disabled={loading || !ready}
      >
        {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        Confirm
      </Button>
    </>
  );
}

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
    <SettingsRow label={label} hint={description}>
      {confirmed ? (
        <ConfirmButtons
          loading={loading}
          ready
          onCancel={onCancel}
          onExecute={onExecute}
        />
      ) : (
        <ClearButton name={label} onClick={onConfirm} />
      )}
    </SettingsRow>
  );
}
