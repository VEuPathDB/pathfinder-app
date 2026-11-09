"use client";

import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { Copy, Eye, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { copySharedConversation } from "@pathfinder/shared/generated/hooks/useCopySharedConversation";
import type { SharedConversation } from "@pathfinder/shared/generated/types/SharedConversation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { toUserMessage } from "@/lib/api/errors";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { chatUrl } from "@/lib/routes";
import { goToSiteSignIn } from "@/lib/siteSignIn";

import {
  passwordHeader,
  sharedHeadOptions,
  sharedMessagesOptions,
  sharedRefusalOf,
} from "./sharedConversation";
import { SharedThread } from "./SharedThread";

export function SharedConversationView({
  token,
  signInUrl,
}: {
  token: string;
  signInUrl: string;
}) {
  const [password, setPassword] = useState<string | null>(null);
  const head = useQuery(sharedHeadOptions(token, password));
  if (head.isPending)
    return (
      <Centered>
        <Spinner className="size-5" />
      </Centered>
    );
  const refusal = head.isError ? sharedRefusalOf(head.error) : null;
  if (refusal !== null && (head.data === undefined || refusal !== "failed")) {
    if (refusal === "locked") {
      return <PasswordForm wrong={password !== null} onOpen={setPassword} />;
    }
    return (
      <Centered>
        <p data-testid="shared-gone" className="text-sm text-muted-foreground">
          {refusal === "gone"
            ? "This link is no longer shared."
            : "This conversation could not be read. Try again in a moment."}
        </p>
      </Centered>
    );
  }
  if (head.data === undefined) return null;
  return (
    <SharedOpen
      token={token}
      password={password}
      head={head.data}
      signInUrl={signInUrl}
    />
  );
}

function Centered({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center bg-card px-4">
      {children}
    </div>
  );
}

function PasswordForm({
  wrong,
  onOpen,
}: {
  wrong: boolean;
  onOpen: (password: string) => void;
}) {
  const [value, setValue] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (value.trim() !== "") onOpen(value.trim());
  };
  return (
    <Centered>
      <form onSubmit={submit} className="w-full max-w-sm space-y-3">
        <p className="text-sm">
          This conversation is shared with a password. Ask the person who sent the link
          for it.
        </p>
        <label className="block space-y-1 text-sm">
          <span>Password</span>
          <Input
            type="password"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            autoComplete="off"
          />
        </label>
        {wrong ? (
          <p role="alert" className="text-xs text-destructive">
            That password does not open this conversation.
          </p>
        ) : null}
        <Button type="submit" size="sm">
          Open
        </Button>
      </form>
    </Centered>
  );
}

function SharedOpen({
  token,
  password,
  head,
  signInUrl,
}: {
  token: string;
  password: string | null;
  head: SharedConversation;
  signInUrl: string;
}) {
  const messages = useQuery({
    ...sharedMessagesOptions(token, password, head.cursor),
    placeholderData: keepPreviousData,
  });
  const [shown, setShown] = useState(messages.data);
  if (messages.data !== undefined && messages.data !== shown) setShown(messages.data);
  const thread = messages.data ?? shown;
  return (
    <div className="flex h-full min-h-0 flex-col bg-card">
      <header
        data-testid="shared-header"
        className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-border px-4 py-3"
      >
        <h1 className="min-w-0 flex-1 truncate text-sm font-medium">{head.name}</h1>
        <span
          data-testid="shared-read-only"
          className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground"
        >
          <Eye className="size-3" aria-hidden />
          Read-only
        </span>
        {head.allowCopy && !head.turnInFlight ? (
          <CopyAction
            token={token}
            password={password}
            siteId={head.siteId}
            signInUrl={signInUrl}
          />
        ) : null}
      </header>
      <div className="min-h-0 flex-1">
        {thread === undefined ? (
          <Centered>
            {messages.isError ? (
              <p
                data-testid="shared-unreadable"
                className="text-sm text-muted-foreground"
              >
                This conversation could not be read. Try again in a moment.
              </p>
            ) : (
              <Spinner className="size-5" />
            )}
          </Centered>
        ) : (
          <SharedThread
            key={thread.cursor}
            id={`shared-${token}`}
            messages={thread.messages}
          />
        )}
      </div>
      {messages.isError && thread !== undefined ? (
        <p
          data-testid="shared-behind"
          className="border-t border-border px-4 py-2 text-xs text-muted-foreground"
        >
          The newest turns could not be read yet. Trying again.
        </p>
      ) : null}
      {head.turnInFlight ? (
        <p
          data-testid="shared-answering"
          className="border-t border-border px-4 py-2 text-xs text-muted-foreground"
        >
          The conversation is answering. The reply shows here when it is done.
        </p>
      ) : null}
    </div>
  );
}

function CopyAction({
  token,
  password,
  siteId,
  signInUrl,
}: {
  token: string;
  password: string | null;
  siteId: string;
  signInUrl: string;
}) {
  const router = useRouter();
  const auth = useQuery({ ...authStatusOptions(siteId), retryOnMount: false });
  const copy = useMutation({
    mutationFn: () =>
      copySharedConversation(token, { siteId }, passwordHeader(password)),
    onSuccess: (made) => router.push(chatUrl(made.id)),
    onError: (error) =>
      toast.error(toUserMessage(error, "Could not copy this conversation")),
  });
  if (auth.data?.signedIn !== true) {
    return (
      <a
        href={signInUrl}
        target="_top"
        onClick={(event) => {
          event.preventDefault();
          goToSiteSignIn(window, signInUrl);
        }}
        className="text-xs underline underline-offset-2"
      >
        Sign in to make a copy
      </a>
    );
  }
  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      disabled={copy.isPending}
      aria-busy={copy.isPending}
      onClick={() => copy.mutate()}
    >
      {copy.isPending ? (
        <Loader2 className="mr-1 size-3.5 animate-spin" aria-hidden />
      ) : (
        <Copy className="mr-1 size-3.5" aria-hidden />
      )}
      Make a copy
    </Button>
  );
}
