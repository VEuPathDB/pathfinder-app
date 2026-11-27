import { finishRun, wireMode } from "./fixtures/wire";

export default async function finishTheWire(): Promise<void> {
  const report = await finishRun();
  if (wireMode() === "replay" && report !== "") {
    throw new Error(report);
  }
}
