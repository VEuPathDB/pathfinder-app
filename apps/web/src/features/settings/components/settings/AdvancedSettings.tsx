"use client";

/**
 * AdvancedSettings -- debug toggles.
 */

import { useShallow } from "zustand/react/shallow";
import { resetAllPersistedSettings, useSettingsStore } from "@/state/useSettingsStore";
import { SettingsField } from "./SettingsField";

export function AdvancedSettings() {
  const {
    showRawToolCalls,
    setShowRawToolCalls,
    showTokenUsage,
    setShowTokenUsage,
    deleteFromWdk,
    setDeleteFromWdk,
  } = useSettingsStore(
    useShallow((s) => ({
      showRawToolCalls: s.showRawToolCalls,
      setShowRawToolCalls: s.setShowRawToolCalls,
      showTokenUsage: s.showTokenUsage,
      setShowTokenUsage: s.setShowTokenUsage,
      deleteFromWdk: s.deleteFromWdk,
      setDeleteFromWdk: s.setDeleteFromWdk,
    })),
  );

  function handleResetAll() {
    const confirmed = window.confirm(
      "Reset all local settings? This clears your model, sidebar, and app preferences and reloads the page.",
    );
    if (!confirmed) return;
    resetAllPersistedSettings();
    window.location.reload();
  }

  return (
    <div className="space-y-5">
      <SettingsField label="Also delete on VEuPathDB">
        <label className="inline-flex cursor-pointer items-center gap-2 text-sm">
          <input
            data-testid="delete-from-wdk-checkbox"
            type="checkbox"
            checked={deleteFromWdk}
            onChange={(e) => setDeleteFromWdk(e.target.checked)}
            className="h-4 w-4 rounded border-input text-foreground focus:ring-ring"
          />
          <span className="text-muted-foreground">
            Deleting a conversation in the sidebar starts with Also delete strategy
            checked, so its strategy is deleted on the site too. You can uncheck it for
            one delete.
          </span>
        </label>
      </SettingsField>

      <SettingsField label="Show token usage">
        <label className="inline-flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={showTokenUsage}
            onChange={(e) => setShowTokenUsage(e.target.checked)}
            className="h-4 w-4 rounded border-input text-foreground focus:ring-ring"
          />
          <span className="text-muted-foreground">
            Display token counts under each message
          </span>
        </label>
      </SettingsField>

      <SettingsField label="Show raw tool calls in the conversation">
        <label className="inline-flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={showRawToolCalls}
            onChange={(e) => setShowRawToolCalls(e.target.checked)}
            className="h-4 w-4 rounded border-input text-foreground focus:ring-ring"
          />
          <span className="text-muted-foreground">
            Display raw JSON tool calls in the conversation
          </span>
        </label>
      </SettingsField>

      <div className="space-y-2 border-t border-border pt-4">
        <button
          type="button"
          onClick={handleResetAll}
          className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition hover:border-destructive/40 hover:bg-destructive/5 hover:text-destructive"
        >
          Reset all local settings
        </button>
        <p className="text-[11px] text-muted-foreground">
          Clears model, sidebar, and app preferences stored in this browser. Your
          server-side preferences (models, quota) are unaffected.
        </p>
      </div>
    </div>
  );
}
