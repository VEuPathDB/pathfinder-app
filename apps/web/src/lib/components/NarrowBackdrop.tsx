import { cn } from "@/lib/utils/cn";

export function NarrowBackdrop({
  label,
  onClose,
  className,
}: {
  label: string;
  onClose: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClose}
      className={cn("absolute inset-y-0 z-30 bg-black/30", className)}
    />
  );
}
