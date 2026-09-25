/**
 * @vitest-environment jsdom
 */
import {
  AssistantRuntimeProvider,
  ThreadPrimitive,
  useLocalRuntime,
} from "@assistant-ui/react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { UserAttachments } from "./UserAttachments";

const PNG_URL = "data:image/png;base64,iVBORw0KGgo=";
const PDF_URL = "data:application/pdf;base64,JVBERg==";

function Thread() {
  const runtime = useLocalRuntime(
    {
      async run() {
        return { content: [] };
      },
    },
    {
      initialMessages: [
        {
          role: "user",
          content: "which genes are in these?",
          attachments: [
            {
              id: "0",
              type: "image",
              name: "table.png",
              contentType: "image/png",
              status: { type: "complete" },
              content: [{ type: "image", image: PNG_URL }],
            },
            {
              id: "1",
              type: "document",
              name: "paper.pdf",
              contentType: "application/pdf",
              status: { type: "complete" },
              content: [{ type: "file", data: PDF_URL, mimeType: "application/pdf" }],
            },
          ],
        },
      ],
    },
  );
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Messages components={{ Message: UserAttachments }} />
    </AssistantRuntimeProvider>
  );
}

describe("UserAttachments", () => {
  it("draws an image as a thumbnail and a PDF as a named chip", () => {
    render(<Thread />);
    expect(screen.getByTestId("user-attachment-image")).toHaveAttribute(
      "alt",
      "table.png",
    );
    expect(screen.getByTestId("user-attachment-image")).toHaveAttribute("src", PNG_URL);
    expect(screen.getByTestId("user-attachment-file")).toHaveTextContent("paper.pdf");
  });
});
