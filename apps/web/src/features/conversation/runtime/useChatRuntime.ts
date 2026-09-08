"use client";

import { useChat } from "@ai-sdk/react";
import { useState } from "react";
import {
  type UIMessage,
  lastAssistantMessageIsCompleteWithApprovalResponses,
} from "ai";
import { useAISDKRuntime } from "@assistant-ui/react-ai-sdk";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import type { Strategy } from "@pathfinder/shared";
import { graphClearedSchema } from "@pathfinder/shared/generated/zod/graphClearedSchema";
import { graphSnapshotSchema } from "@pathfinder/shared/generated/zod/graphSnapshotSchema";
import { strategyMetaSchema } from "@pathfinder/shared/generated/zod/strategyMetaSchema";
import { turnUsageSchema } from "@pathfinder/shared/generated/zod/turnUsageSchema";

import { resumeDurableThread } from "@pathfinder/assistant-client/ai-sdk";

import { getAuthHeaders } from "@/lib/api/http";
import { beginStrategy } from "@pathfinder/shared/generated/hooks/useBeginStrategy";
import { listStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListStrategies";
import { strategyQueryKey, strategyQueryOptions } from "@/lib/api/strategy";
import { getMyQuotaQueryKey } from "@pathfinder/shared/generated/hooks/useGetMyQuota";
import { listScratchpadNotesQueryOptions } from "@pathfinder/shared/generated/hooks/useListScratchpadNotes";
import { handleWdkAuthRefusal } from "@/state/useAuthGateStore";
import { useRightRailStore } from "@/state/useRightRailStore";
import { useSessionStore } from "@/state/useSessionStore";
import { useSettingsStore } from "@/state/useSettingsStore";
import { useStrategyStore } from "@/state/strategy/store";

import { buildChatRequestBody } from "./buildRequestBody";
import type { ChatHelpers } from "./chatHelpersContext";
import { createDurableTransport } from "./durableTransport";
import { GeneIdAttachmentAdapter } from "./geneIdAttachmentAdapter";

interface UseChatRuntimeArgs {
  conversationId: string;
  initialMessages?: UIMessage[];
  resume?: boolean;
}

export function useChatRuntime({
  conversationId,
  initialMessages,
  resume = false,
}: UseChatRuntimeArgs): {
  runtime: ReturnType<typeof useAISDKRuntime<UIMessage>>;
  chat: ChatHelpers;
} {
  const queryClient = useQueryClient();
  const invalidateConversationList = () => {
    const siteId = useSessionStore.getState().selectedSite;
    void queryClient.invalidateQueries({
      queryKey: listStrategiesQueryOptions({ siteId }).queryKey,
    });
  };
  const openMessageId = openAssistantMessageId(initialMessages);
  const [transport] = useState(() =>
    createDurableTransport({
      conversationId,
      eventsUrlFor: (id) => `/api/v1/conversations/${id}/events`,
      api: "/api/v1/chat",
      ...(openMessageId === undefined ? {} : { openMessageId }),
      headers: () =>
        getAuthHeaders({
          accept: "text/event-stream",
          contentType: "application/json",
        }),
      prepareSendMessagesRequest: async ({ id, messages, trigger, body }) => {
        const siteId = useSessionStore.getState().selectedSite;
        const { phaseModels, phaseReasoning } = useSettingsStore.getState();
        await beginStrategy(conversationId, { siteId });
        return {
          body: buildChatRequestBody({
            conversationId,
            siteId,
            id,
            trigger,
            messages,
            baseBody: body as Record<string, unknown> | undefined,
            phaseModels,
            phaseReasoning,
          }),
        };
      },
    }),
  );

  const chatApi = useChat<UIMessage>({
    id: conversationId,
    generateId: () => crypto.randomUUID(),
    ...(initialMessages !== undefined && { messages: initialMessages }),
    transport,
    sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithApprovalResponses,
    onData: (dataPart) => {
      switch (dataPart.type) {
        case "data-conversation-title":
          invalidateConversationList();
          break;
        case "data-scratchpad-updated":
          void queryClient.invalidateQueries({
            queryKey: listScratchpadNotesQueryOptions(conversationId).queryKey,
          });
          break;
        case "data-graph-snapshot": {
          const snapshot = graphSnapshotSchema.parse(dataPart.data);
          void queryClient.invalidateQueries({
            queryKey: strategyQueryOptions(conversationId).queryKey,
          });
          // Surface the freshly built strategy: switch the rail to the
          // Strategy panel so the user sees the result of the auto-build.
          if (snapshot.nodes.length > 0) {
            useRightRailStore.getState().openPanelId(conversationId, "strategy", {
              strategyStepCount: snapshot.nodes.length,
            });
          }
          break;
        }
        case "data-strategy-meta":
          strategyMetaSchema.parse(dataPart.data);
          break;
        case "data-graph-cleared":
          graphClearedSchema.parse(dataPart.data);
          useStrategyStore.getState().clear();
          void queryClient.invalidateQueries({
            queryKey: strategyQueryOptions(conversationId).queryKey,
          });
          break;
        case "data-turn-usage": {
          const usage = turnUsageSchema.parse(dataPart.data);
          const detailKey = strategyQueryOptions(conversationId).queryKey;
          queryClient.setQueryData<Strategy | null>(detailKey, (prev) =>
            prev == null
              ? prev
              : {
                  ...prev,
                  totalTokens: usage.totalTokens,
                  totalCostUsd: usage.costUsd,
                },
          );
          void queryClient.invalidateQueries({ queryKey: getMyQuotaQueryKey() });
          break;
        }
      }
    },
    onError: (err) => {
      handleWdkAuthRefusal(err);
    },
    onFinish: () => {
      void queryClient.invalidateQueries({
        queryKey: strategyQueryKey(conversationId),
      });
      invalidateConversationList();
      void queryClient.invalidateQueries({ queryKey: getMyQuotaQueryKey() });
    },
  });

  // A turn the log still holds is read across its turn boundaries: the SDK
  // builds one message per stream, so each turn the tail opens is its own read.
  useQuery({
    queryKey: ["conversations", conversationId, "reattach"],
    queryFn: async () => {
      await resumeDurableThread(chatApi, transport);
      return conversationId;
    },
    enabled: resume,
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
  });

  const runtime = useAISDKRuntime(chatApi, {
    adapters: {
      attachments: new GeneIdAttachmentAdapter(),
    },
  });

  const chat: ChatHelpers = {
    ...chatApi,
    resumeStream: () => resumeDurableThread(chatApi, transport),
  };

  return { runtime, chat };
}

/** The assistant message a reload already holds, which a resume continues. */
function openAssistantMessageId(messages: UIMessage[] | undefined): string | undefined {
  const last = messages?.at(-1);
  return last?.role === "assistant" ? last.id : undefined;
}
