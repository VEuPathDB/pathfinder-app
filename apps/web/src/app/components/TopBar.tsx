"use client";

import Image from "next/image";

import { QuotaPill } from "@/app/components/QuotaPill";
import { SiteAuth } from "@/features/sites/components/SiteAuth";
import { getSiteBanner } from "@/features/sites/siteBanners";

interface TopBarProps {
  selectedSite: string;
}

export function TopBar({ selectedSite }: TopBarProps) {
  const banner = getSiteBanner(selectedSite);

  return (
    <header
      className="relative min-h-11 border-b border-border"
      style={{
        backgroundImage: `url(${banner.imagePath})`,
        backgroundSize: "cover",
        backgroundPosition: "center",
      }}
    >
      <div
        className="absolute inset-0 bg-gradient-to-r from-black/50 via-black/25 to-transparent"
        aria-hidden
      />
      <div className="relative flex flex-wrap items-center justify-between gap-x-3 gap-y-1 px-4 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <Image
            src="/pathfinder.svg"
            alt=""
            width={22}
            height={22}
            className="shrink-0 drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]"
          />
          <span className="truncate text-sm font-semibold tracking-tight text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]">
            PathFinder
          </span>
        </div>
        <div className="flex min-w-0 items-center gap-3">
          <QuotaPill siteId={selectedSite} />
          <SiteAuth siteId={selectedSite} headerTextVariant="light" />
        </div>
      </div>
    </header>
  );
}
