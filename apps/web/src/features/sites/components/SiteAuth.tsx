"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { authStatusOptions, logoutVeupathdb } from "@/lib/api/veupathdb-auth";
import { Modal } from "@/lib/components/Modal";
import { SignInForm } from "@/features/sites/components/SignInForm";
import type { HeaderTextVariant } from "@/features/sites/siteBanners";
import { useHasHydrated } from "@/features/sites/useHasHydrated";
import { invalidateUserScopedQueries } from "@/lib/query/invalidateUserScoped";
import { cn } from "@/lib/utils/cn";

interface SiteAuthProps {
  siteId: string;
  authDisplay?: "button" | "inline";
  headerTextVariant?: HeaderTextVariant;
}

export function SiteAuth({
  siteId,
  authDisplay = "button",
  headerTextVariant,
}: SiteAuthProps) {
  const [showLoginModal, setShowLoginModal] = useState(false);
  const queryClient = useQueryClient();

  const { data: authStatus } = useQuery(authStatusOptions(siteId));

  const hasHydrated = useHasHydrated();
  const signedIn = authStatus?.signedIn === true;
  const displaySignedIn = hasHydrated && signedIn;
  const displayName = authStatus?.name ?? "";

  const refreshAfterAuthChange = async () => {
    await queryClient.invalidateQueries({
      queryKey: authStatusOptions(siteId).queryKey,
    });
    invalidateUserScopedQueries(queryClient);
  };

  const lightClass =
    "text-white/95 drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)] transition-colors duration-150 hover:text-primary hover:drop-shadow-none";
  const darkClass =
    "text-muted-foreground transition-colors duration-150 hover:text-foreground";
  const actionClass = headerTextVariant === "light" ? lightClass : darkClass;

  return (
    <>
      {displaySignedIn && (
        <div className={cn("flex items-center gap-3 text-xs")}>
          <span
            className={
              headerTextVariant === "light"
                ? "text-white/95 drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]"
                : "text-muted-foreground"
            }
          >
            Logged in as {displayName !== "" ? displayName : "—"}
          </span>
          <button
            type="button"
            onClick={() => {
              void (async () => {
                try {
                  await logoutVeupathdb(siteId);
                  await refreshAfterAuthChange();
                } catch {
                  console.warn("[SiteAuth] Failed to log out");
                }
              })();
            }}
            className={actionClass}
          >
            Log out
          </button>
        </div>
      )}

      {authDisplay === "button" && !displaySignedIn && (
        <button
          type="button"
          onClick={() => setShowLoginModal(true)}
          className={cn("text-xs", actionClass)}
        >
          Sign in →
        </button>
      )}

      {authDisplay === "inline" && !displaySignedIn && (
        <div className="mt-4">
          <SignInForm
            onSuccess={() => {
              void refreshAfterAuthChange();
            }}
          />
        </div>
      )}

      <Modal
        open={showLoginModal}
        onClose={() => setShowLoginModal(false)}
        title="Sign in to VEuPathDB"
        maxWidth="max-w-sm"
        showCloseButton
      >
        <div className="p-5">
          <SignInForm
            onSuccess={() => {
              setShowLoginModal(false);
              void refreshAfterAuthChange();
            }}
          />
        </div>
      </Modal>
    </>
  );
}
