import { DATA_STATEMENT_VERSION } from "@pathfinder/shared";

export const YOUR_DATA_LAST_UPDATED = new Date(
  `${DATA_STATEMENT_VERSION}T00:00:00Z`,
).toLocaleDateString("en-US", {
  timeZone: "UTC",
  year: "numeric",
  month: "long",
  day: "numeric",
});

export const YOUR_DATA_IN_BRIEF: readonly string[] = [
  "Your messages, the files you attach and what PathFinder read from VEuPathDB to answer you go to an AI model provider: OpenAI by default, or the provider of the model you pick. A few small requests, such as naming a conversation, go to OpenAI whichever model you pick.",
  "Results and counts come from VEuPathDB's own searches. Each strategy PathFinder builds is a normal VEuPathDB strategy in your account, which you can open on the site and check.",
  "The AI can be wrong. It can choose the wrong search or misread your question.",
  "PathFinder keeps your conversations, gene sets and memories until you delete them. The team may read a conversation to find and fix a problem, whatever you choose for learning.",
  "Learning from your strategies is your choice. If it is on, PathFinder may use copies of your conversations and strategies to improve PathFinder for everyone: people on the team read them, and parts can become test cases or shared examples the assistant draws on when helping other researchers. Shared copies never carry your name or account. You can change this at any time in Settings, on the Privacy tab.",
  "You can use your own OpenAI, Anthropic or Google key. PathFinder stores it sealed and sends it only to its provider.",
  "Questions or concerns: write to help@veupathdb.org.",
];
