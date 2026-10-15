"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { toUserMessage } from "@/lib/api/errors";
import { authStatusOptions, logoutVeupathdb } from "@/lib/api/veupathdb-auth";
import { invalidateUserScopedQueries } from "@/lib/query/invalidateUserScoped";

export function RailSignOut({ siteId }: { siteId: string }) {
  const queryClient = useQueryClient();

  const signOut = async () => {
    try {
      await logoutVeupathdb(siteId);
    } catch (err) {
      toast.error(`Sign-out failed: ${toUserMessage(err)}`);
      return;
    }
    invalidateUserScopedQueries(queryClient);
    await queryClient.invalidateQueries({
      queryKey: authStatusOptions(siteId).queryKey,
    });
  };

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => {
            void signOut();
          }}
          aria-label="Sign out"
        >
          <LogOut className="h-4 w-4" aria-hidden />
        </Button>
      </TooltipTrigger>
      <TooltipContent side="right">Sign out</TooltipContent>
    </Tooltip>
  );
}
