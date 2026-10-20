import { redirect } from "next/navigation";

import { chatRoot } from "@/lib/routes";

export default function RootPage() {
  redirect(chatRoot());
}
