import type { Metadata } from "next";

import { YourDataPage } from "@/features/help/YourDataPage";

export const metadata: Metadata = { title: "Your data in VEuPathDB Strategist" };

export default function Page() {
  return <YourDataPage />;
}
