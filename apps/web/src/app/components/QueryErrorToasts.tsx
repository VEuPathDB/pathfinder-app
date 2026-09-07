"use client";

import { toast } from "sonner";

import { setQueryErrorHandler } from "@/lib/query/client";
import { handleWdkAuthRefusal } from "@/state/useAuthGateStore";

/**
 * Sends a failed query to a toast, or to the sign-in request when the refusal
 * is about the VEuPathDB account. Every app shell mounts this, including on a
 * site that answers nothing, where the sign-in prompt itself does not render.
 */
export function QueryErrorToasts(): null {
  setQueryErrorHandler((notice) => {
    if (handleWdkAuthRefusal(notice.error, notice.retry)) return;
    toast.error(notice.message);
  });
  return null;
}
