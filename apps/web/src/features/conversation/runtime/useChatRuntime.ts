"use client";

import { useChat } from "@ai-sdk/react";
import { toast } from "sonner";
import { useState } from "react";
import {
  type UIMessage,
  lastAssistantMessageIsCompleteWithApprovalResponses,
} from "ai";
import { useAISDKRuntime } from "@assistant-ui/react-ai-sdk";
import { useIsFetching, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Strategy } from "@pathfinder/shared";
import { graphClearedSchema } from "@pathfinder/shared/generated/zod/graphClearedSchema";
import { graphSnapshotSchema } from "@pathfinder/shared/generated/zod/graphSnapshotSchema";
import { strategyMetaSchema } from "@pathfinder/shared/generated/zod/strategyMetaSchema";
import { turnUsageSchema } from "@pathfinder/shared/generated/zod/turnUsageSchema";

import { resumeDurableThread } from "@veupathdb/assistant-client/ai-sdk";

import { getAuthHeaders } from "@/lib/api/http";
import { listStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListStrategies";
import { refetchStrategy, strategyQueryOptions } from "@/lib/api/strategy";
import { getMyQuotaQueryKey } from "@pathfinder/shared/generated/hooks/useGetMyQuota";
import { listScratchpadNotesQueryOptions } from "@pathfinder/shared/generated/hooks/useListScratchpadNotes";
import { handleWdkAuthRefusal } from "@/state/useAuthGateStore";
import { useRightRailStore } from "@/state/useRightRailStore";
import { useSessionStore } from "@/state/useSessionStore";
import { useSettingsStore } from "@/state/useSettingsStore";
import { useStrategyStore } from "@/state/strategy/store";

import { conversationCursors } from "../api/assistantClient";
import { beginConversation } from "../api/beginConversation";

import { buildChatRequestBody } from "./buildRequestBody";
import type { ChatHelpers } from "./chatHelpersContext";
import { createDurableTransport } from "./durableTransport";
import { GeneIdAttachmentAdapter } from "./geneIdAttachmentAdapter";

/** The turn a snapshot reports in flight, before any message of it is open. */
const SNAPSHOT_TURN = "snapshot-turn";

export const THREAD_STOPPED_FOLLOWING =
  "This thread stopped following the work it has running; reload the page to read where that work got to.";

function reattachKey(conversationId: string): string[] {
  return ["conversations", conversationId, "reattach"];
}

interface UseChatRuntimeArgs {
  conversationId: string;
  initialMessages?: UIMessage[];
  resume?: boolean;
  /** The snapshot ended at a prompt, so the thread has a turn to follow. */
  turnInFlight?: boolean;
  /** The assistant this thread runs under. */
  assistantId?: string;
}

export function useChatRuntime({
  conversationId,
  initialMessages,
  resume = false,
  turnInFlight = false,
  assistantId,
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
  const [transport] = useState(() =>
    createDurableTransport({
      conversationId,
      eventsUrlFor: (id) => `/api/v1/conversations/${id}/events`,
      api: "/api/v1/chat",
      headers: () =>
        getAuthHeaders({
          accept: "text/event-stream",
          contentType: "application/json",
        }),
      prepareSendMessagesRequest: async ({ id, messages, trigger, body }) => {
        const siteId = useSessionStore.getState().selectedSite;
        const { phaseModels, phaseReasoning } = useSettingsStore.getState();
        const begun = await beginConversation(conversationId, {
          siteId,
          ...(assistantId !== undefined && { assistantId }),
        });
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
            // A thread keeps the assistant it was created with, so only the
            // message that created it names one.
            ...(begun.isNew && assistantId !== undefined && { assistantId }),
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
          void refetchStrategy(queryClient, conversationId);
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
          void refetchStrategy(queryClient, conversationId);
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
      if (handleWdkAuthRefusal(err)) return;
      // The thread's own turn draws its error; a refused follow draws nothing,
      // so the user is told that the work it was reading runs on unread.
      if (queryClient.isFetching({ queryKey: reattachKey(conversationId) }) > 0) {
        toast.error(THREAD_STOPPED_FOLLOWING);
      }
    },
    onFinish: () => {
      void refetchStrategy(queryClient, conversationId);
      invalidateConversationList();
      void queryClient.invalidateQueries({ queryKey: getMyQuotaQueryKey() });
    },
  });

  // The thread has one turn to follow at a time: the one the snapshot found
  // running when this view opened, and then every message a park leaves open.
  const [snapshotTurn, setSnapshotTurn] = useState(() => resume && turnInFlight);
  const openMessageId = conversationCursors.readOpenMessage(conversationId)?.messageId;
  const turnToFollow = openMessageId ?? (snapshotTurn ? SNAPSHOT_TURN : null);
  // Every turn boundary the log delivers grants one follow. The cursor stands
  // still while a tail reports no turn in flight, so a silent thread is read
  // once and not polled. It is state, so the key advances with it.
  const [delivered, setDelivered] = useState(() =>
    conversationCursors.read(conversationId),
  );
  const following = useIsFetching({ queryKey: reattachKey(conversationId) }) > 0;

  // A tail on an idle thread ends a turn started meanwhile, so a thread reads
  // only while it holds no stream of its own.
  useQuery({
    queryKey: [...reattachKey(conversationId), turnToFollow, delivered],
    queryFn: async () => {
      await resumeDurableThread(chatApi, transport);
      setDelivered(conversationCursors.read(conversationId));
      setSnapshotTurn(false);
      return turnToFollow;
    },
    enabled: turnToFollow !== null && !following && chatApi.status === "ready",
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
  });

  const runtime = useAISDKRuntime(chatApi, {
    adapters: {
      attachments: new GeneIdAttachmentAdapter(),
    },
  });

  return { runtime, chat: chatApi };
}
