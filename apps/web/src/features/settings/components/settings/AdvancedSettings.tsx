"use client";

import { useShallow } from "zustand/react/shallow";
import { resetAllPersistedSettings, useSettingsStore } from "@/state/useSettingsStore";
import { Button } from "@/components/ui/button";

import { SettingsRow, SettingsSection, SettingsSwitch } from "./SettingsRow";

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
    <div className="space-y-8">
      <SettingsSection title="Conversations">
        <SettingsSwitch
          testId="delete-from-wdk-checkbox"
          label="Also delete on VEuPathDB"
          hint="Deleting a conversation also deletes its strategy on the site."
          checked={deleteFromWdk}
          onCheckedChange={setDeleteFromWdk}
        />
        <SettingsSwitch
          label="Show token usage"
          hint="Token counts under each message."
          checked={showTokenUsage}
          onCheckedChange={setShowTokenUsage}
        />
        <SettingsSwitch
          label="Show raw tool calls"
          hint="Raw JSON tool calls in the conversation."
          checked={showRawToolCalls}
          onCheckedChange={setShowRawToolCalls}
        />
      </SettingsSection>

      <SettingsSection title="This browser">
        <SettingsRow
          label="Reset local settings"
          hint="Model, sidebar and app preferences kept in this browser."
        >
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleResetAll}
            aria-label="Reset all local settings"
            className="hover:border-destructive/40 hover:text-destructive"
          >
            Reset
          </Button>
        </SettingsRow>
      </SettingsSection>
    </div>
  );
}
