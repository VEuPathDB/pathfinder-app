interface AutoOpenInput {
  hasUserMessage: boolean;
  conversationId: string;
  autoOpenedConversation: string | null;
  autoOpenChecked: string | null;
  narrowViewport: boolean;
}

/** Whether the rail opens itself on the ledger for this thread. */
export function shouldAutoOpenLedger({
  hasUserMessage,
  conversationId,
  autoOpenedConversation,
  autoOpenChecked,
  narrowViewport,
}: AutoOpenInput): boolean {
  return (
    hasUserMessage &&
    !narrowViewport &&
    autoOpenedConversation !== conversationId &&
    autoOpenChecked !== conversationId
  );
}
