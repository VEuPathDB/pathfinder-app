"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { chatRoot } from "@/lib/routes";
import { type SettingsTab, useSettingsModalStore } from "@/state/useSettingsModalStore";

export function SettingsTabLink({
  tab,
  children,
}: {
  tab: SettingsTab;
  children: ReactNode;
}) {
  const openSettings = useSettingsModalStore((s) => s.open);
  return (
    <Link
      href={chatRoot()}
      onClick={() => openSettings(tab)}
      className="text-primary underline underline-offset-2"
    >
      {children}
    </Link>
  );
}
