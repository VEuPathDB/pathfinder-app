"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { toast } from "sonner";
import { deleteShare } from "@pathfinder/shared/generated/hooks/useDeleteShare";
import { getShareQueryOptions } from "@pathfinder/shared/generated/hooks/useGetShare";
import { postSharePassword } from "@pathfinder/shared/generated/hooks/usePostSharePassword";
import { putShare } from "@pathfinder/shared/generated/hooks/usePutShare";
import type { ShareChange } from "@pathfinder/shared/generated/types/ShareChange";
import type { ShareSettings } from "@pathfinder/shared/generated/types/ShareSettings";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toUserMessage } from "@/lib/api/errors";
import { sitesOptions } from "@/lib/api/sites";
import { hostingSite } from "@/lib/sites/hostingSite";

import { shareUrl } from "./shareUrl";

const NO_SETTINGS: ShareSettings = { public: false, allowCopy: false };

export function ShareDialog({
  conversationId,
  open,
  onOpenChange,
}: {
  conversationId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const options = getShareQueryOptions(conversationId);
  const state = useQuery({ ...options, enabled: open });
  const { data: sites } = useQuery(sitesOptions());
  const [draft, setDraft] = useState<ShareSettings>(NO_SETTINGS);
  const [password, setPassword] = useState<string | null>(null);

  const refused = (error: unknown) =>
    toast.error(toUserMessage(error, "Could not change the share link"));
  const changed = (change: ShareChange) => {
    queryClient.setQueryData(options.queryKey, { share: change.share });
    setPassword(change.share.public ? null : (change.password ?? password));
  };
  const save = useMutation({
    mutationFn: (settings: ShareSettings) => putShare(conversationId, settings),
    onSuccess: changed,
    onError: refused,
  });
  const renew = useMutation({
    mutationFn: () => postSharePassword(conversationId),
    onSuccess: changed,
    onError: refused,
  });
  const stop = useMutation({
    mutationFn: () => deleteShare(conversationId),
    onSuccess: () => {
      queryClient.setQueryData(options.queryKey, { share: null });
      setPassword(null);
      setDraft(NO_SETTINGS);
    },
    onError: refused,
  });

  const share = state.data?.share ?? null;
  const settings: ShareSettings =
    share === null ? draft : { public: share.public, allowCopy: share.allowCopy };
  const busy = save.isPending || renew.isPending || stop.isPending;
  const change = (next: ShareSettings) =>
    share === null ? setDraft(next) : save.mutate(next);
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const pageUrl = hostingSite(sites ?? [], origin)?.pageUrl ?? null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Share this conversation</DialogTitle>
          <DialogDescription>
            People with the link see this conversation as it continues. They cannot send
            messages or change your strategy.
          </DialogDescription>
        </DialogHeader>
        {state.isPending ? null : (
          <div className="space-y-4 text-sm">
            <div className="space-y-2">
              <Choice
                label="Anyone with the link can open it"
                hint="Otherwise the link needs a password that PathFinder makes."
                checked={settings.public}
                disabled={busy}
                onChange={(value) => change({ ...settings, public: value })}
              />
              <Choice
                label="Let people copy it into their own account"
                hint="A signed-in viewer can make their own copy to continue."
                checked={settings.allowCopy}
                disabled={busy}
                onChange={(value) => change({ ...settings, allowCopy: value })}
              />
            </div>
            {share === null ? (
              <Button
                type="button"
                size="sm"
                disabled={busy}
                onClick={() => save.mutate(draft)}
              >
                Create link
              </Button>
            ) : (
              <div className="space-y-3">
                <CopyField
                  label="Link"
                  value={shareUrl(share.token, pageUrl, origin)}
                  copyLabel="Copy link"
                  copied="Link copied"
                />
                {share.public ? null : password !== null ? (
                  <CopyField
                    label="Password"
                    value={password}
                    copyLabel="Copy password"
                    copied="Password copied"
                    note="Copy it now. It is not shown again."
                  />
                ) : (
                  <p
                    data-testid="share-password-hidden"
                    className="text-xs text-muted-foreground"
                  >
                    The password was shown when it was made. Make a new one to share it
                    again; the old one stops working.
                  </p>
                )}
                <div className="flex flex-wrap justify-between gap-2">
                  {share.public ? (
                    <span />
                  ) : (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() => renew.mutate()}
                    >
                      New password
                    </Button>
                  )}
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="text-destructive hover:text-destructive"
                    disabled={busy}
                    onClick={() => stop.mutate()}
                  >
                    Stop sharing
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Choice({
  label,
  hint,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  disabled: boolean;
  onChange: (value: boolean) => void;
}) {
  const id = useId();
  return (
    <div className="flex items-start gap-2">
      <Checkbox
        id={id}
        checked={checked}
        disabled={disabled}
        onCheckedChange={(value) => onChange(value === true)}
        className="mt-0.5"
      />
      <div>
        <Label htmlFor={id}>{label}</Label>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
    </div>
  );
}

function CopyField({
  label,
  value,
  copyLabel,
  copied,
  note,
}: {
  label: string;
  value: string;
  copyLabel: string;
  copied: string;
  note?: string;
}) {
  const id = useId();
  const copy = () =>
    navigator.clipboard.writeText(value).then(
      () => toast.success(copied),
      () => toast.error("Could not copy. Select the text and copy it instead."),
    );
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex gap-2">
        <Input
          id={id}
          readOnly
          value={value}
          onFocus={(event) => event.target.select()}
          className="text-xs"
        />
        <Button type="button" size="sm" variant="outline" onClick={() => void copy()}>
          {copyLabel}
        </Button>
      </div>
      {note === undefined ? null : (
        <p className="text-xs text-muted-foreground">{note}</p>
      )}
    </div>
  );
}
