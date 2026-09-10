import { describe, expect, it } from "vitest";
import { latestRevision, revisionOfMessage } from "./SupersededBadge";

/**
 * A turn's counts were true when it was written. Editing the strategy
 * afterwards leaves them on screen with nothing marking them historical, so a
 * researcher reads a stale gene count as current fact - no error, no zero,
 * nothing to notice.
 *
 * The backend has stamped every turn with `data-strategy-revision` all along;
 * this is the comparison that finally uses it.
 */

function assistant(...revisions: (string | null)[]) {
  return {
    role: "assistant",
    content: revisions.map((revision) =>
      revision === null
        ? { type: "text", text: "hello" }
        : { type: "data-strategy-revision", data: { revision } },
    ),
  };
}

describe("revisionOfMessage", () => {
  it("reads the revision a turn was stamped with", () => {
    expect(revisionOfMessage(assistant("abc123"))).toBe("abc123");
  });

  it("ignores a user message", () => {
    expect(revisionOfMessage({ role: "user", content: [{ type: "text" }] })).toBe(null);
  });

  it("returns null when the turn carried no revision", () => {
    expect(revisionOfMessage(assistant(null))).toBe(null);
  });

  it("takes the last revision when a turn emitted several", () => {
    expect(revisionOfMessage(assistant("first", "second"))).toBe("second");
  });

  it("treats an empty revision as absent", () => {
    // An empty fingerprint is what `strategy_revision` returns for no
    // strategy at all; that is not something a message can be stale against.
    expect(revisionOfMessage(assistant(""))).toBe(null);
  });

  it("also accepts the generic data part shape", () => {
    expect(
      revisionOfMessage({
        role: "assistant",
        content: [
          { type: "data", name: "strategy-revision", data: { revision: "xyz" } },
        ],
      }),
    ).toBe("xyz");
  });
});

describe("latestRevision", () => {
  it("is the newest revision any turn reported", () => {
    const thread = {
      messages: [assistant("old"), assistant("new")],
    };

    expect(latestRevision(thread)).toBe("new");
  });

  it("skips later turns that carried no revision", () => {
    const thread = {
      messages: [assistant("old"), assistant(null)],
    };

    expect(latestRevision(thread)).toBe("old");
  });

  it("is null for a thread that never mentioned a strategy", () => {
    expect(latestRevision({ messages: [assistant(null)] })).toBe(null);
  });

  it("is null for an empty thread", () => {
    expect(latestRevision({ messages: [] })).toBe(null);
    expect(latestRevision(undefined)).toBe(null);
  });
});

describe("what counts as superseded", () => {
  it("an older turn is superseded once the strategy changes", () => {
    const older = assistant("rev1");
    const thread = { messages: [older, assistant("rev2")] };

    expect(revisionOfMessage(older)).not.toBe(latestRevision(thread));
  });

  it("the newest turn is never superseded by itself", () => {
    const newest = assistant("rev2");
    const thread = { messages: [assistant("rev1"), newest] };

    expect(revisionOfMessage(newest)).toBe(latestRevision(thread));
  });

  it("a refreshed count does not supersede anything", () => {
    // strategy_revision hashes inputs only, so re-reading WDK produces the
    // same fingerprint and nothing is marked historical.
    const thread = { messages: [assistant("same"), assistant("same")] };

    expect(revisionOfMessage(thread.messages[0])).toBe(latestRevision(thread));
  });
});
