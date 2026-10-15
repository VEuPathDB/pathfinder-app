/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  AssistantRuntimeProvider,
  ThreadPrimitive,
  useExternalStoreRuntime,
} from "@assistant-ui/react";
import type { ThreadMessageLike } from "@assistant-ui/react";

import { ChatHelpersProvider, type ChatHelpers } from "../runtime/chatHelpersContext";
import { AssistantMessage, UserMessage } from "./MessageRenderer";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/orthomcl/conversation/conv-1",
}));

const STUB_CHAT = { messages: [], status: "ready" } as unknown as ChatHelpers;
const SEQUENCE =
  "MPENNEHLTFLYAAITIIGLLMVENMFVHCSHSHHHHDKEINTLEEAHHHEVIETEKNENELVEEDDFNQHHFESLKDLKNPFQIGILLGALSLHSLLEGLDNHCNSTPIATVGLFMHKMTDSLSAGLALSKGTMSKGTALKFLFAFCCVTPLFMCIGASIRTYIDKTFLEPLLKGLSLGSLLYVIFFENIATKLHGKSVTKKLLFTLIGLLLGSFFIIKTHGQH";
const MESSAGE = `BLAST this protein.\n\n>query\n${SEQUENCE}`;

function Thread({ messages }: { messages: ThreadMessageLike[] }) {
  const runtime = useExternalStoreRuntime<ThreadMessageLike>({
    messages,
    convertMessage: (message) => message,
    onNew: async () => undefined,
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ChatHelpersProvider value={STUB_CHAT}>
        <ThreadPrimitive.Messages components={{ AssistantMessage, UserMessage }} />
      </ChatHelpersProvider>
    </AssistantRuntimeProvider>
  );
}

describe("a researcher's message", () => {
  it("shows a pasted FASTA record as typed, wrapping the sequence", async () => {
    render(<Thread messages={[{ role: "user", content: MESSAGE }]} />);

    const text = await screen.findByText(/BLAST this protein\./);
    expect(text.textContent).toBe(MESSAGE);
    expect(text).toHaveClass("whitespace-pre-wrap", "break-words");
    expect(document.querySelector("blockquote")).toBeNull();
  });
});

describe("an assistant reply", () => {
  it("breaks a word longer than the reply's width", async () => {
    render(
      <Thread
        messages={[
          { role: "user", content: "hi" },
          { role: "assistant", content: `The hit is ${SEQUENCE}.` },
        ]}
      />,
    );

    const reply = await screen.findByText(/The hit is/);
    expect(reply.closest(".prose")).toHaveClass("break-words");
  });
});
