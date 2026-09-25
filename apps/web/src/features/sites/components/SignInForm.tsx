"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  authStatusOptions,
  getVeupathdbAuthStatus,
  loginVeupathdb,
} from "@/lib/api/veupathdb-auth";
import { siteUnavailableRefusal, toUserMessage } from "@/lib/api/errors";
import { SiteUnavailableNotice } from "@/features/sites/components/SiteUnavailableNotice";
import { useSessionStore } from "@/state/useSessionStore";
import { Input } from "@/components/ui/input";

interface SignInFormProps {
  /** Called when sign-in succeeds. */
  onSuccess?: () => void;
}

/** What the form says after a refused sign-in. */
type SignInRefusal = { kind: "message"; text: string } | { kind: "site-unavailable" };

/** VEuPathDB sign-in form: email and password against the selected site. */
export function SignInForm({ onSuccess }: SignInFormProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [refusal, setRefusal] = useState<SignInRefusal | null>(null);
  const [authBusy, setAuthBusy] = useState(false);

  const selectedSite = useSessionStore((state) => state.selectedSite);
  const queryClient = useQueryClient();

  const handleSubmit = async () => {
    setRefusal(null);
    setAuthBusy(true);
    try {
      await loginVeupathdb(email, password, selectedSite);
      const status = await getVeupathdbAuthStatus(selectedSite);
      if (status.signedIn) {
        queryClient.setQueryData(authStatusOptions(selectedSite).queryKey, status);
        onSuccess?.();
      } else {
        setRefusal({
          kind: "message",
          text: "Login failed. Please check your credentials.",
        });
      }
    } catch (err) {
      setRefusal(
        siteUnavailableRefusal(err) !== null
          ? { kind: "site-unavailable" }
          : {
              kind: "message",
              text: toUserMessage(err, "Login failed. Please try again."),
            },
      );
    } finally {
      setAuthBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="space-y-2.5">
        <Input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
        />
        <Input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !authBusy) void handleSubmit();
          }}
        />
      </div>
      {refusal?.kind === "message" && (
        <div className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {refusal.text}
        </div>
      )}
      {refusal?.kind === "site-unavailable" && (
        <SiteUnavailableNotice siteId={selectedSite} />
      )}
      <button
        type="button"
        disabled={authBusy}
        onClick={() => {
          void handleSubmit();
        }}
        className="w-full rounded-md bg-primary px-3 py-2.5 text-sm font-semibold text-primary-foreground shadow-sm transition-all duration-150 hover:bg-primary/90 hover:-translate-y-px active:translate-y-0 disabled:opacity-60"
      >
        {authBusy ? "Signing in..." : "Sign in"}
      </button>
      <p className="text-center text-[11px] text-muted-foreground">
        We do not store your login credentials.
      </p>
    </div>
  );
}
