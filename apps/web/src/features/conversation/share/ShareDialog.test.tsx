/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { createTestWrapper } from "@/lib/query/testing";

import { server } from "../../../../vitest.msw-setup";
import { ShareDialog } from "./ShareDialog";

const CONVERSATION = "4f1c2a3b-5d6e-4f70-8a9b-0c1d2e3f4a5b";
const SHARE = `http://localhost:3000/pathfinder/api/v1/conversations/${CONVERSATION}/share`;
const TOKEN = "tok-abcdefghijklmnopqrstuvwxyz0123456789";

interface Stored {
  token: string;
  public: boolean;
  allowCopy: boolean;
}

function serve(initial: Stored | null) {
  let stored = initial;
  let minted = 0;
  const puts: unknown[] = [];
  const deletes: string[] = [];
  server.use(
    http.get(SHARE, () => HttpResponse.json({ share: stored })),
    http.put(SHARE, async ({ request }) => {
      const body = (await request.json()) as { public: boolean; allowCopy: boolean };
      puts.push(body);
      const mint = !body.public && (stored === null || stored.public);
      stored = { token: TOKEN, public: body.public, allowCopy: body.allowCopy };
      minted += mint ? 1 : 0;
      return HttpResponse.json({
        share: stored,
        password: mint ? `pw-${minted}` : null,
      });
    }),
    http.post(`${SHARE}/password`, () => {
      minted += 1;
      return HttpResponse.json({ share: stored, password: `pw-${minted}` });
    }),
    http.delete(SHARE, ({ request }) => {
      deletes.push(request.url);
      stored = null;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return { puts, deletes };
}

function open() {
  const { Wrapper } = createTestWrapper();
  return render(
    <ShareDialog conversationId={CONVERSATION} open onOpenChange={() => undefined} />,
    { wrapper: Wrapper },
  );
}

const writeText = vi.fn(async () => undefined);

beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
});

afterEach(() => {
  writeText.mockClear();
});

describe("ShareDialog", () => {
  it("makes a link behind a password unless anyone may open it", async () => {
    const { puts } = serve(null);
    open();

    await userEvent.click(await screen.findByRole("button", { name: "Create link" }));

    expect(puts).toEqual([{ public: false, allowCopy: false }]);
    expect(await screen.findByLabelText("Password")).toHaveValue("pw-1");
    expect(screen.getByLabelText("Link")).toHaveValue(
      `http://localhost:3000/pathfinder/shared/${TOKEN}`,
    );
  });

  it("makes an open link when the box is ticked", async () => {
    const { puts } = serve(null);
    open();

    await userEvent.click(
      await screen.findByRole("checkbox", { name: "Anyone with the link can open it" }),
    );
    await userEvent.click(
      screen.getByRole("checkbox", {
        name: "Let people copy it into their own account",
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Create link" }));

    expect(puts).toEqual([{ public: true, allowCopy: true }]);
    await screen.findByLabelText("Link");
    expect(screen.queryByLabelText("Password")).toBeNull();
  });

  it("copies the link", async () => {
    serve({ token: TOKEN, public: true, allowCopy: false });
    open();

    await userEvent.click(await screen.findByRole("button", { name: "Copy link" }));

    expect(writeText).toHaveBeenCalledWith(
      `http://localhost:3000/pathfinder/shared/${TOKEN}`,
    );
  });

  it("says a private link's password is not shown again and makes a new one", async () => {
    serve({ token: TOKEN, public: false, allowCopy: false });
    open();

    expect(await screen.findByTestId("share-password-hidden")).toHaveTextContent(
      "The password was shown when it was made.",
    );
    await userEvent.click(screen.getByRole("button", { name: "New password" }));

    expect(await screen.findByLabelText("Password")).toHaveValue("pw-1");
  });

  it("saves a changed box at once", async () => {
    const { puts } = serve({ token: TOKEN, public: true, allowCopy: false });
    open();

    await userEvent.click(
      await screen.findByRole("checkbox", {
        name: "Let people copy it into their own account",
      }),
    );

    await waitFor(() => expect(puts).toEqual([{ public: true, allowCopy: true }]));
  });

  it("stops sharing", async () => {
    const { deletes } = serve({ token: TOKEN, public: true, allowCopy: false });
    open();

    await userEvent.click(await screen.findByRole("button", { name: "Stop sharing" }));

    await waitFor(() => expect(deletes).toHaveLength(1));
    expect(
      await screen.findByRole("button", { name: "Create link" }),
    ).toBeInTheDocument();
  });
});
