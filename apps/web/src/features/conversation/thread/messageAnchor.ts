/** The DOM id of the message a link can jump to. */
export function messageAnchorId(messageId: string): string {
  return `message-${messageId}`;
}
