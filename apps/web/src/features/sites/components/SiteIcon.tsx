import Image from "next/image";
import { cn } from "@/lib/utils/cn";

interface SiteIconProps {
  siteId: string;
  size?: number;
  className?: string;
}

/**
 * Renders the VEuPathDB organism icon for a given site ID.
 *
 * Falls back to the VEuPathDB portal icon for unknown IDs.
 */
export function SiteIcon({ siteId, size = 24, className }: SiteIconProps) {
  const slug = siteId.toLowerCase();
  const src = `/icons/${slug}.png`;
  const fallback = "/icons/veupathdb.png";

  return (
    <span
      className={cn("inline-block shrink-0 overflow-hidden rounded-full", className)}
      style={{ width: size, height: size }}
    >
      <Image
        src={src}
        alt=""
        width={size}
        height={size}
        className="h-full w-full object-contain"
        onError={(e) => {
          e.currentTarget.src = fallback;
        }}
      />
    </span>
  );
}
