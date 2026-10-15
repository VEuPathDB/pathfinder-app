/**
 * The VEuPathDB sign-in gate. Every WDK-backed feature needs a registered
 * VEuPathDB login, so this store carries the open sign-in prompt and the
 * reason the server gave for it.
 */

import { toast } from "sonner";

import { wdkAuthRefusal } from "@/lib/api/errors";
import { createStore } from "./middleware";

interface AuthGateState {
  signInRequired: boolean;
  /** The server's explanation, or null while no prompt is open. */
  signInReason: string | null;

  requestSignIn: (reason: string) => void;
  dismissSignIn: () => void;
}

export const useAuthGateStore = createStore<AuthGateState>("AuthGateStore", (set) => ({
  signInRequired: false,
  signInReason: null,

  requestSignIn: (reason) =>
    set((s) => {
      if (s.signInRequired && s.signInReason === reason) return s;
      return { signInRequired: true, signInReason: reason };
    }),

  dismissSignIn: () =>
    set((s) =>
      s.signInRequired || s.signInReason !== null
        ? { signInRequired: false, signInReason: null }
        : s,
    ),
}));

/** One toast for the whole gate, so concurrent refusals replace it. */
export const WDK_LOGIN_REQUIRED_TOAST_ID = "wdk-login-required";

function promptSignIn(detail: string): void {
  toast.error(detail, { id: WDK_LOGIN_REQUIRED_TOAST_ID });
  useAuthGateStore.getState().requestSignIn(detail);
}

/**
 * Route a refusal about the caller's VEuPathDB account to the sign-in prompt.
 * Returns false for every other error, which stays with its own handler.
 */
export function handleWdkAuthRefusal(err: unknown): boolean {
  const refusal = wdkAuthRefusal(err);
  if (refusal === null) return false;
  promptSignIn(refusal.detail);
  return true;
}
