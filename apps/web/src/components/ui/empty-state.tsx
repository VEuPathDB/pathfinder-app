import * as React from "react";

import { cn } from "@/lib/utils/cn";

function EmptyState({
  icon,
  heading,
  description,
  action,
  className,
}: {
  icon?: React.ReactNode;
  heading: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      data-slot="empty-state"
      className={cn("flex h-full items-center justify-center", className)}
    >
      <div className="max-w-sm animate-fade-in text-center">
        {icon != null && (
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center text-muted-foreground">
            {icon}
          </div>
        )}
        <h2 className="text-base font-semibold text-foreground">{heading}</h2>
        {description != null && description !== "" && (
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            {description}
          </p>
        )}
        {action != null && <div className="mt-5">{action}</div>}
      </div>
    </div>
  );
}

export { EmptyState };
