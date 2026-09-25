"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  getMyProviderKeysQueryKey,
  getMyProviderKeysQueryOptions,
} from "@pathfinder/shared/generated/hooks/useGetMyProviderKeys";
import { getMyQuotaQueryKey } from "@pathfinder/shared/generated/hooks/useGetMyQuota";
import { putMyProviderKeyMutationOptions } from "@pathfinder/shared/generated/hooks/usePutMyProviderKey";
import { deleteMyProviderKeyMutationOptions } from "@pathfinder/shared/generated/hooks/useDeleteMyProviderKey";
import type { KeyableProvider } from "@pathfinder/shared/generated/types/KeyableProvider";
import type { ProviderKeyView } from "@pathfinder/shared/generated/types/ProviderKeyView";
import { toUserMessage } from "@/lib/api/errors";

import { SettingsField } from "./SettingsField";

const PROVIDERS: readonly { id: KeyableProvider; name: string }[] = [
  { id: "openai", name: "OpenAI" },
  { id: "anthropic", name: "Anthropic" },
  { id: "google", name: "Google" },
];

const dateFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });

function standing(stored: ProviderKeyView | undefined, name: string): string {
  if (stored === undefined)
    return "No key. The deployment's key is used, if it has one.";
  if (stored.status === "active") {
    return `...${stored.hint}, added ${dateFmt.format(new Date(stored.createdAt))}.`;
  }
  if (stored.refusal === "unreadable") {
    return `...${stored.hint} can no longer be read. Enter it again.`;
  }
  if (stored.refusal === "no_credit") {
    return `...${stored.hint}: This key has no credit. Add credit to the ${name} account, or replace the key.`;
  }
  if (stored.refusal === "forbidden") {
    return `...${stored.hint} is not permitted by ${name} to run its models. Replace it or remove it.`;
  }
  return `...${stored.hint} was refused by ${name}. Replace it or remove it.`;
}

/** Tell the views that read a payer or a spend that the keys changed. */
function useKeysChanged(): () => Promise<void> {
  const qc = useQueryClient();
  return async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: getMyProviderKeysQueryKey() }),
      qc.invalidateQueries({ queryKey: getMyQuotaQueryKey() }),
    ]);
  };
}

function KeyRow({
  provider,
  name,
  stored,
}: {
  provider: KeyableProvider;
  name: string;
  stored: ProviderKeyView | undefined;
}) {
  const keysChanged = useKeysChanged();
  const [draft, setDraft] = useState("");
  const [refusal, setRefusal] = useState<string | null>(null);
  // The key rides the mutation's variables, so the mutation is dropped as
  // soon as it settles and no cache keeps it.
  const save = useMutation({
    ...putMyProviderKeyMutationOptions(),
    gcTime: 0,
    onError: (err) => setRefusal(toUserMessage(err, "The key was not saved.")),
    onSuccess: keysChanged,
  });
  const remove = useMutation({
    ...deleteMyProviderKeyMutationOptions(),
    onSuccess: keysChanged,
  });

  return (
    <div className="space-y-2 rounded-md border border-border px-3 py-2.5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="text-sm font-medium text-foreground">{name}</div>
          <div className="text-xs text-muted-foreground">{standing(stored, name)}</div>
        </div>
        {stored !== undefined && (
          <button
            type="button"
            aria-label={`Remove ${name} key`}
            disabled={remove.isPending}
            onClick={() => remove.mutate({ provider })}
            className="rounded-md border border-input px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
          >
            Remove
          </button>
        )}
      </div>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          const key = draft.trim();
          if (key === "") return;
          setDraft("");
          setRefusal(null);
          save.mutate({ provider, data: { key } }, { onSettled: () => save.reset() });
        }}
      >
        <input
          type="password"
          aria-label={`${name} key`}
          autoComplete="off"
          spellCheck={false}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={stored === undefined ? "Paste a key" : "Paste a new key"}
          className="min-w-0 flex-1 rounded-md border border-input bg-background px-2.5 py-1.5 text-sm outline-none"
        />
        <button
          type="submit"
          aria-label={`Save ${name} key`}
          disabled={save.isPending || draft.trim() === ""}
          className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
        >
          {save.isPending ? "Checking..." : "Save"}
        </button>
      </form>
      {refusal !== null && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {refusal}
        </div>
      )}
    </div>
  );
}

export function ProviderKeySettings() {
  const { data } = useQuery(getMyProviderKeysQueryOptions());
  if (data == null) return null;

  return (
    <div className="space-y-4">
      <SettingsField label="Your own provider keys">
        <p className="text-sm leading-relaxed text-muted-foreground">
          A key you add pays for every model of its provider, and PathFinder checks it
          with one short request before saving it. It is stored sealed, never shown
          again, and spend on it does not count against your monthly allowance.
        </p>
      </SettingsField>
      {data.enabled ? (
        PROVIDERS.map(({ id, name }) => (
          <KeyRow
            key={id}
            provider={id}
            name={name}
            stored={data.keys.find((stored) => stored.provider === id)}
          />
        ))
      ) : (
        <p className="text-sm text-muted-foreground">
          This deployment does not accept personal keys.
        </p>
      )}
    </div>
  );
}
