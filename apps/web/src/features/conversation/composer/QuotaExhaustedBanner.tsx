"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleAlert } from "lucide-react";
import { useSearchParams } from "next/navigation";

import { getMyQuotaQueryOptions } from "@pathfinder/shared/generated/hooks/useGetMyQuota";
import { listModelsQueryOptions } from "@pathfinder/shared/generated/hooks/useListModels";
import { listTiersQueryOptions } from "@pathfinder/shared/generated/hooks/useListTiers";
import { resolveAssistantId } from "@/lib/assistants";
import { useProviderPayers } from "@/lib/hooks/useProviderPayers";
import {
  assistantRoles,
  refusedProvidersInUse,
  rolesPaidByDeployment,
} from "@/lib/models/payers";
import { ASSISTANT_PARAM } from "@/lib/routes";
import { useConversationDetail } from "@/state/useConversationExists";
import { useSettingsStore } from "@/state/useSettingsStore";

const dateFmt = new Intl.DateTimeFormat("en-US", {
  month: "long",
  day: "numeric",
  year: "numeric",
});

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const PROVIDER_NAMES: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  google: "Google",
};

interface ComposerBlock {
  /** The allowance is spent and some stage of this turn draws on it. */
  allowanceSpent: boolean;
  /** Providers whose refused key some stage of this turn would run on. */
  refusedInUse: string[];
  blocked: boolean;
  /** What the composer's field says while the block holds. */
  placeholder: string | null;
}

/**
 * Whether the next message can be paid for. The server decides; this reads
 * the same payer rule so the composer does not offer a send it will refuse.
 */
export function useComposerBlock(conversationId: string): ComposerBlock {
  const searchParams = useSearchParams();
  const { data: detail } = useConversationDetail(conversationId);
  const assistantId = resolveAssistantId({
    existing: detail?.assistantId,
    requested: searchParams.get(ASSISTANT_PARAM),
  });
  const { data: quota } = useQuery(getMyQuotaQueryOptions());
  const { data: models } = useQuery(listModelsQueryOptions());
  const { data: tiers } = useQuery(listTiersQueryOptions());
  const { payers, refused } = useProviderPayers();
  const picks = useSettingsStore((s) => s.phaseModels);

  const roles = assistantRoles(tiers?.presets, assistantId);
  const defaults = models?.phaseDefaults ?? {};
  const limit = Number(quota?.limitUsd ?? 0);
  const spent = quota != null && limit > 0 && Number(quota.usedUsd) >= limit;
  const allowanceSpent =
    spent && rolesPaidByDeployment(roles, picks, defaults, payers).length > 0;
  const refusedInUse = refusedProvidersInUse(roles, picks, defaults, refused);
  const placeholder =
    refusedInUse.length > 0
      ? "A key you added was refused - replace it in Settings."
      : allowanceSpent
        ? "Monthly quota reached - try again after the reset date."
        : null;
  return {
    allowanceSpent,
    refusedInUse,
    blocked: placeholder !== null,
    placeholder,
  };
}

export function QuotaExhaustedBanner({ conversationId }: { conversationId: string }) {
  const { data } = useQuery(getMyQuotaQueryOptions());
  const { allowanceSpent } = useComposerBlock(conversationId);
  if (data == null || !allowanceSpent) return null;
  const used = Number(data.usedUsd);
  const limit = Number(data.limitUsd);

  return (
    <div
      role="alert"
      data-testid="quota-exhausted-banner"
      className="mx-auto flex w-full max-w-3xl items-start gap-3 border-t border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm text-destructive"
    >
      <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-medium">Monthly quota reached</p>
        <p className="mt-0.5 text-xs text-destructive">
          You&apos;ve used {currency.format(used)} of your {currency.format(limit)}{" "}
          monthly limit. New messages are paused until{" "}
          {dateFmt.format(new Date(data.resetsAt))}, unless every stage runs on a key
          you added in Settings, under Provider keys.
        </p>
      </div>
    </div>
  );
}

export function RefusedKeyBanner({ conversationId }: { conversationId: string }) {
  const { refusedInUse } = useComposerBlock(conversationId);
  if (refusedInUse.length === 0) return null;
  const names = refusedInUse.map((provider) => PROVIDER_NAMES[provider] ?? provider);

  return (
    <div
      role="alert"
      data-testid="refused-key-banner"
      className="mx-auto flex w-full max-w-3xl items-start gap-3 border-t border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm text-destructive"
    >
      <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
      <p className="min-w-0 flex-1 text-xs">
        {names.join(" and ")} refused the key you added. Replace or remove it in
        Settings, under Provider keys.
      </p>
    </div>
  );
}

/** The two reasons a turn cannot be paid for, each shown when it holds. */
export function PaymentBanners({ conversationId }: { conversationId: string }) {
  return (
    <>
      <QuotaExhaustedBanner conversationId={conversationId} />
      <RefusedKeyBanner conversationId={conversationId} />
    </>
  );
}
