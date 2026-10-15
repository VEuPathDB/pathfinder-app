import { useId, type ReactNode } from "react";

import { Switch } from "@/components/ui/switch";

export function SettingsSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="space-y-1">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      {description !== undefined && (
        <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
      )}
      <div className="divide-y divide-border/60 pt-1">{children}</div>
    </section>
  );
}

export function SettingsRow({
  label,
  hint,
  children,
}: {
  label: ReactNode;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-6 py-3">
      <div className="min-w-0">
        <div className="text-sm font-medium text-foreground">{label}</div>
        {hint !== undefined && (
          <div className="mt-0.5 text-xs text-muted-foreground">{hint}</div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">{children}</div>
    </div>
  );
}

export function SettingsSwitch({
  label,
  hint,
  checked,
  disabled,
  onCheckedChange,
  testId,
}: {
  label: string;
  hint?: ReactNode;
  checked: boolean;
  disabled?: boolean;
  onCheckedChange: (checked: boolean) => void;
  testId?: string;
}) {
  const id = useId();
  return (
    <SettingsRow label={<label htmlFor={id}>{label}</label>} hint={hint}>
      <Switch
        id={id}
        data-testid={testId}
        checked={checked}
        disabled={disabled}
        onCheckedChange={onCheckedChange}
      />
    </SettingsRow>
  );
}
