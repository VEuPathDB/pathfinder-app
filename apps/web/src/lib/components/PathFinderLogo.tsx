import Image from "next/image";

import { withBasePath } from "@/lib/basePath";
import { BRAND } from "@/lib/brand";
import { cn } from "@/lib/utils/cn";

interface PathFinderLogoProps {
  size: number;
  label?: string;
  priority?: boolean;
  className?: string;
}

export function PathFinderLogo({
  size,
  label,
  priority = false,
  className,
}: PathFinderLogoProps) {
  const named = label !== undefined;
  return (
    <span
      role={named ? "img" : undefined}
      aria-label={label}
      aria-hidden={named ? undefined : true}
      className={cn("inline-flex shrink-0", className)}
      style={{ width: size, height: size }}
    >
      <Image
        src={withBasePath(BRAND.markLight)}
        alt=""
        width={size}
        height={size}
        priority={priority}
        className="dark:hidden"
      />
      <Image
        src={withBasePath(BRAND.markDark)}
        alt=""
        width={size}
        height={size}
        priority={priority}
        className="hidden dark:block"
      />
    </span>
  );
}
