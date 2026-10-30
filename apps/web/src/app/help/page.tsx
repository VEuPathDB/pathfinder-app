import type { Metadata } from "next";

import { HelpRoute } from "./HelpRoute";

export const metadata: Metadata = { title: "Help - PathFinder" };

export default function Page() {
  return <HelpRoute />;
}
