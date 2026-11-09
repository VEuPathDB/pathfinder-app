"use client";

import { useChat } from "@ai-sdk/react";
import { AssistantRuntimeProvider, ThreadPrimitive } from "@assistant-ui/react";
import { useAISDKRuntime } from "@assistant-ui/react-ai-sdk";
import type { UIMessage } from "ai";

import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";

import { AssistantMessage, UserMessage } from "../content/MessageRenderer";
import { ReadOnlyThreadProvider } from "../readOnlyThread";
import { ChatHelpersProvider } from "../runtime/chatHelpersContext";

export function SharedThread({ id, messages }: { id: string; messages: UIMessage[] }) {
  const chat = useChat({ id, messages });
  const runtime = useAISDKRuntime(chat);
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ChatHelpersProvider value={chat}>
        <ReadOnlyThreadProvider value>
          <ThreadPrimitive.Root className="flex h-full min-h-0 flex-col">
            <Conversation>
              <ConversationContent className="pt-4">
                <ThreadPrimitive.Messages
                  components={{ UserMessage, AssistantMessage }}
                />
              </ConversationContent>
            </Conversation>
            <ConversationScrollButton />
          </ThreadPrimitive.Root>
        </ReadOnlyThreadProvider>
      </ChatHelpersProvider>
    </AssistantRuntimeProvider>
  );
}
