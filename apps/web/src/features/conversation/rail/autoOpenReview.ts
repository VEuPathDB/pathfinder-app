interface AutoOpenInput {
  hasUserMessage: boolean;
  conversationId: string;
  autoOpenedConversation: string | null;
  autoOpenChecked: string | null;
}

/** Whether the rail opens itself on Review for this thread. */
export function shouldAutoOpenReview({
  hasUserMessage,
  conversationId,
  autoOpenedConversation,
  autoOpenChecked,
}: AutoOpenInput): boolean {
  return (
    hasUserMessage &&
    autoOpenedConversation !== conversationId &&
    autoOpenChecked !== conversationId
  );
}
