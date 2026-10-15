"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
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
import { yourDataUrl } from "@/lib/routes";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { SettingsRow, SettingsSection } from "./SettingsRow";

const PROVIDERS: readonly { id: KeyableProvider; name: string }[] = [
  { id: "openai", name: "OpenAI" },
  { id: "anthropic", name: "Anthropic" },
  { id: "google", name: "Google" },
];

const dateFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });

function standing(stored: ProviderKeyView | undefined, name: string): string {
  if (stored === undefined)
    return "Not set. The deployment's key is used, if it has one.";
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
    <div className="py-3">
      <SettingsRow label={name} hint={standing(stored, name)}>
        <form
          className="flex items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const key = draft.trim();
            if (key === "") return;
            setDraft("");
            setRefusal(null);
            save.mutate({ provider, data: { key } }, { onSettled: () => save.reset() });
          }}
        >
          <Input
            type="password"
            aria-label={`${name} key`}
            autoComplete="off"
            spellCheck={false}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={stored === undefined ? "Paste a key" : "Paste a new key"}
            className="h-8 w-44 text-sm"
          />
          <Button
            type="submit"
            size="sm"
            aria-label={`Save ${name} key`}
            disabled={save.isPending || draft.trim() === ""}
          >
            {save.isPending ? "Checking..." : "Save"}
          </Button>
          {stored !== undefined && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label={`Remove ${name} key`}
              disabled={remove.isPending}
              onClick={() => remove.mutate({ provider })}
              className="text-muted-foreground"
            >
              Remove
            </Button>
          )}
        </form>
      </SettingsRow>
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
    <SettingsSection
      title="Your own provider keys"
      description={
        <>
          A key pays for its provider&apos;s models, outside your monthly allowance.
          PathFinder checks it once, stores it sealed and never shows it again.{" "}
          <Link
            href={yourDataUrl("your-key")}
            className="text-foreground underline underline-offset-2"
          >
            Your data in PathFinder
          </Link>
        </>
      }
    >
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
        <p className="py-3 text-sm text-muted-foreground">
          This deployment does not accept personal keys.
        </p>
      )}
    </SettingsSection>
  );
}
