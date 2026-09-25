export interface ParsedSlash {
  token: string;
  rest: string;
}

export function parseSlashInput(value: string): ParsedSlash | null {
  if (!value.startsWith("/")) return null;
  const after = value.slice(1);
  const spaceIdx = after.indexOf(" ");
  if (spaceIdx === -1) return { token: after, rest: "" };
  return { token: after.slice(0, spaceIdx), rest: after.slice(spaceIdx + 1) };
}

export function matchCommandName(
  token: string,
  candidate: { name: string; aliases?: string[] },
): boolean {
  const lower = token.toLowerCase();
  if (candidate.name.toLowerCase() === lower) return true;
  const aliases = candidate.aliases ?? [];
  return aliases.some((a) => a.toLowerCase() === lower);
}

export function fuzzyPrefix(
  token: string,
  candidate: { name: string; aliases?: string[] },
): boolean {
  const lower = token.toLowerCase();
  if (candidate.name.toLowerCase().startsWith(lower)) return true;
  const aliases = candidate.aliases ?? [];
  return aliases.some((a) => a.toLowerCase().startsWith(lower));
}

export function filterCommands<T extends { name: string; aliases?: string[] }>(
  commands: readonly T[],
  token: string,
): T[] {
  return commands.filter((c) => fuzzyPrefix(token, c));
}

/**
 * The token of a slash input that no command's name or alias starts with, or
 * null. The token is the text after the opening slash, up to the first space.
 */
export function unknownCommandToken(
  value: string,
  commands: readonly { name: string; aliases?: string[] }[],
): string | null {
  const parsed = parseSlashInput(value);
  if (parsed === null || parsed.token === "") return null;
  return filterCommands(commands, parsed.token).length === 0 ? parsed.token : null;
}
