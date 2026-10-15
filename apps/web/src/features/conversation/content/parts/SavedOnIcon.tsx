import { siteShortName } from "@pathfinder/shared";

import { SiteIcon } from "@/lib/components/SiteIcon";

export function SavedOnIcon({ siteId }: { siteId: string }) {
  const label = `Saved on ${siteShortName(siteId)}`;
  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      data-site-id={siteId}
      className="inline-flex shrink-0"
    >
      <SiteIcon siteId={siteId} size={14} />
    </span>
  );
}
