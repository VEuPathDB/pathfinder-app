/** A message id the server wrote is a UUID; a message the client made up for
 * a turn that never reached the server carries another shape. */
const SERVER_MESSAGE_ID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isServerMessageId(id: string): boolean {
  return SERVER_MESSAGE_ID.test(id);
}
