import type { Metadata } from "next";

import { YourDataPage } from "@/features/help/YourDataPage";

export const metadata: Metadata = { title: "Your data in PathFinder" };

export default function Page() {
  return <YourDataPage />;
}
