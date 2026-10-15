"use client";

import { usePathname, useSearchParams } from "next/navigation";

export function useAddressPath(): string {
  const pathname = usePathname();
  const search = useSearchParams().toString();
  return search ? `${pathname}?${search}` : pathname;
}
