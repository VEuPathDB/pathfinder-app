"use client";

import { useQueryClient } from "@tanstack/react-query";
import Image from "next/image";
import Link from "next/link";

import { SignInForm } from "@/features/sites/components/SignInForm";
import { withBasePath } from "@/lib/basePath";
import { invalidateUserScopedQueries } from "@/lib/query/invalidateUserScoped";
import { yourDataUrl } from "@/lib/routes";
import { useAuthGateStore } from "@/state/useAuthGateStore";

const STANDING_TEXT = "Sign in to VEuPathDB to build and manage search strategies.";

export function SignedOutNotice({ reason }: { reason?: string | null }) {
  const queryClient = useQueryClient();
  const dismissSignIn = useAuthGateStore((s) => s.dismissSignIn);

  return (
    <div data-testid="signed-out-notice" className="overflow-hidden rounded-xl">
      <div className="bg-gradient-to-br from-primary/10 via-primary/5 to-transparent px-6 pb-4 pt-6">
        <div className="flex items-center gap-3">
          <Image src={withBasePath("/pathfinder.svg")} alt="" width={36} height={36} />
          <div>
            <div className="text-base font-semibold tracking-tight text-foreground">
              PathFinder
            </div>
            <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              VEuPathDB Strategy Builder
            </div>
          </div>
        </div>
        <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
          {reason != null && reason !== "" ? reason : STANDING_TEXT}
        </p>
      </div>

      <div className="border-t border-border px-6 py-5">
        <SignInForm
          onSuccess={() => {
            dismissSignIn();
            invalidateUserScopedQueries(queryClient);
          }}
        />
        <Link
          href={yourDataUrl()}
          className="mt-3 block text-center text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
        >
          Your data in PathFinder
        </Link>
      </div>
    </div>
  );
}
