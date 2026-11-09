import type { Metadata } from "next";

import { SharedRoute } from "./SharedRoute";

export const metadata: Metadata = { title: "Shared conversation - PathFinder" };

export default function Page() {
  return <SharedRoute />;
}
