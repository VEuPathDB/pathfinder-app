"use client";

import { useId } from "react";

import { Modal } from "@/lib/components/Modal";
import { useAuthGateStore } from "@/state/useAuthGateStore";
import { SignedOutNotice } from "./SignedOutNotice";

interface VeupathdbSignInGateProps {
  /** True while the session has no VEuPathDB login of its own. */
  forced: boolean;
}

/**
 * The one sign-in prompt of an app shell. ``QueryErrorToasts`` sets the store
 * flag this reads, so a route refused for want of a VEuPathDB login opens the
 * prompt from any shell that renders this.
 */
export function VeupathdbSignInGate({ forced }: VeupathdbSignInGateProps) {
  const signInRequired = useAuthGateStore((s) => s.signInRequired);
  const signInReason = useAuthGateStore((s) => s.signInReason);
  const dismissSignIn = useAuthGateStore((s) => s.dismissSignIn);
  const headingId = useId();

  if (forced) {
    return (
      <section
        aria-labelledby={headingId}
        className="flex h-full items-center justify-center bg-background px-6 text-foreground"
      >
        <h1 id={headingId} className="sr-only">
          Sign in to VEuPathDB
        </h1>
        <div className="w-full max-w-md rounded-xl border border-border bg-card shadow-lg">
          <SignedOutNotice />
        </div>
      </section>
    );
  }

  return (
    <Modal
      open={signInRequired}
      onClose={dismissSignIn}
      title="Sign in to VEuPathDB"
      maxWidth="max-w-md"
      showCloseButton
    >
      <SignedOutNotice reason={signInReason} />
    </Modal>
  );
}
