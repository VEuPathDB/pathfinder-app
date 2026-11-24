import type { RailSource } from "./railSource";

export function railSourceFixture(overrides: Partial<RailSource> = {}): RailSource {
  return {
    key: "conv-1",
    siteId: "plasmodb",
    strategy: null,
    privateInputs: {},
    study: null,
    activeTasks: [],
    owner: {
      conversationId: "conv-1",
      strategy: {
        openEditor: () => undefined,
        openStep: () => undefined,
        refresh: { run: () => undefined, pending: false },
        saveStep: () => undefined,
        insertSavedAt: () => undefined,
        insertSavedAsRoot: () => undefined,
        dialogs: null,
      },
      openStudy: () => undefined,
    },
    ...overrides,
  };
}
