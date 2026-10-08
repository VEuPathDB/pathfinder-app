"use client";

import type { MouseEvent } from "react";
import Image from "next/image";
import { usePathname, useSearchParams } from "next/navigation";

import { useSystemConfig } from "@/app/hooks/useSystemConfig";
import { withBasePath } from "@/lib/basePath";
import { goToSiteSignIn, signInHref } from "@/lib/siteSignIn";

const STANDING_TEXT = "Sign in to VEuPathDB to build and manage search strategies.";

function opensElsewhere(event: MouseEvent<HTMLAnchorElement>): boolean {
  return (
    event.button !== 0 ||
    event.metaKey ||
    event.ctrlKey ||
    event.shiftKey ||
    event.altKey
  );
}

export function SignedOutNotice({ reason }: { reason?: string | null }) {
  const { siteSignInUrl } = useSystemConfig();
  const pathname = usePathname();
  const query = useSearchParams().toString();
  const here = withBasePath(query === "" ? pathname : `${pathname}?${query}`);

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
        <a
          href={signInHref(siteSignInUrl, here)}
          target="_top"
          onClick={(event) => {
            if (opensElsewhere(event)) return;
            event.preventDefault();
            goToSiteSignIn(window, siteSignInUrl);
          }}
          className="block w-full rounded-md bg-primary px-3 py-2.5 text-center text-sm font-semibold text-primary-foreground shadow-sm transition-all duration-150 hover:-translate-y-px hover:bg-primary/90 active:translate-y-0"
        >
          Sign in to VEuPathDB
        </a>
      </div>
    </div>
  );
}
