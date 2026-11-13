"use client";

import type { MouseEvent } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { useSitePages } from "@/app/hooks/useSitePages";
import { withBasePath } from "@/lib/basePath";
import { StrategistLogo } from "@/lib/components/StrategistLogo";
import { yourDataUrl } from "@/lib/routes";
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
  const { signInUrl } = useSitePages();
  const pathname = usePathname();
  const query = useSearchParams().toString();
  const here = withBasePath(query === "" ? pathname : `${pathname}?${query}`);

  return (
    <div data-testid="signed-out-notice" className="overflow-hidden rounded-xl">
      <div className="bg-gradient-to-br from-primary/10 via-primary/5 to-transparent px-6 pb-4 pt-6">
        <div className="flex items-center gap-3">
          <StrategistLogo size={36} />
          <div>
            <div className="text-[0.6875rem] font-medium uppercase tracking-wider text-muted-foreground">
              VEuPathDB
            </div>
            <div className="text-base font-semibold tracking-tight text-foreground">
              Strategist
            </div>
          </div>
        </div>
        <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
          {reason != null && reason !== "" ? reason : STANDING_TEXT}
        </p>
      </div>

      <div className="border-t border-border px-6 py-5">
        <a
          href={signInHref(signInUrl, here)}
          target="_top"
          onClick={(event) => {
            if (opensElsewhere(event)) return;
            event.preventDefault();
            goToSiteSignIn(window, signInUrl);
          }}
          className="block w-full rounded-md bg-primary px-3 py-2.5 text-center text-sm font-semibold text-primary-foreground shadow-sm transition-all duration-150 hover:-translate-y-px hover:bg-primary/90 active:translate-y-0"
        >
          Sign in to VEuPathDB
        </a>
        <Link
          href={yourDataUrl()}
          className="mt-3 block text-center text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
        >
          Your data in Strategist
        </Link>
      </div>
    </div>
  );
}
