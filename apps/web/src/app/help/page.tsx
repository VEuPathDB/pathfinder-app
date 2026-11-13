import type { Metadata } from "next";

import { HelpRoute } from "./HelpRoute";

export const metadata: Metadata = { title: "Help - VEuPathDB Strategist" };

export default function Page() {
  return <HelpRoute />;
}
