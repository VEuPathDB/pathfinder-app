/**
 * The catalog entries web tests name. The api's catalog owns the lineup and the
 * web reads it from `GET /api/v1/models`, so a refresh edits this file alone.
 */
function fixture(id: string, name: string) {
  return { id, name, modelName: id.slice(id.indexOf(":") + 1) } as const;
}

export const DEFAULT_MODEL = fixture("openai:gpt-5.6-luna", "GPT-5.6 Luna");
export const OPENAI_FLAGSHIP = fixture("openai:gpt-6-sol", "GPT-6 Sol");
export const OPENAI_SMALL = fixture("openai:gpt-6-luna", "GPT-6 Luna");
export const GOOGLE_STANDARD = fixture("google:gemini-3.8-flash", "Gemini 3.8 Flash");
export const ANTHROPIC_SMALL = fixture(
  "anthropic:claude-haiku-4-5",
  "Claude Haiku 4.5",
);
