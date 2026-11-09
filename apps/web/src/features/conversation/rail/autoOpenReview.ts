interface AutoOpenInput {
  hasUserMessage: boolean;
  conversationId: string;
  autoOpenedConversation: string | null;
  autoOpenChecked: string | null;
  railWouldFloat: boolean;
}

/** Whether the rail opens itself on Review for this thread. */
export function shouldAutoOpenReview({
  hasUserMessage,
  conversationId,
  autoOpenedConversation,
  autoOpenChecked,
  railWouldFloat,
}: AutoOpenInput): boolean {
  return (
    hasUserMessage &&
    !railWouldFloat &&
    autoOpenedConversation !== conversationId &&
    autoOpenChecked !== conversationId
  );
}
