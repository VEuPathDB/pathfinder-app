"use client";

import { useRef } from "react";
import { useReactFlow } from "@xyflow/react";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEventListener } from "usehooks-ts";
import { useStrategyGraphCtx } from "@/features/strategy/graph/StrategyGraphContext";
import { useAddStepMutation } from "@/features/strategy/mutations";
import { chatUrl, strategyCanvasUrl } from "@/lib/routes";

interface UseStrategyKeyboardShortcutsArgs {
  onOpenQuickSwitcher: () => void;
  onToggleShortcutsOverlay: () => void;
}

const LEADER_TIMEOUT_MS = 1000;

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return false;
}

export function useStrategyKeyboardShortcuts({
  onOpenQuickSwitcher,
  onToggleShortcutsOverlay,
}: UseStrategyKeyboardShortcutsArgs): void {
  const ctx = useStrategyGraphCtx();
  const { fitView, zoomIn, zoomOut } = useReactFlow();
  const router = useRouter();
  const pathname = usePathname();
  const siteId = String(useParams()["siteId"] ?? "");
  const conversationId = ctx.strategy?.id ?? "";
  const strategyHref = strategyCanvasUrl(siteId, conversationId);
  const chatHref = chatUrl(siteId, conversationId);
  useAddStepMutation(conversationId);

  const leaderRef = useRef<{ key: "g"; expires: number } | null>(null);

  const handleKeyDown = (event: KeyboardEvent): void => {
    if (isTypingTarget(event.target)) return;

    const meta = event.metaKey || event.ctrlKey;

    // Cmd/Ctrl+K - quick switcher
    if (meta && event.key.toLowerCase() === "k") {
      event.preventDefault();
      onOpenQuickSwitcher();
      return;
    }

    // Cmd/Ctrl+A - select all (delegate to browser-default by allowing it to bubble)
    // Cmd/Ctrl+Z handled by useStrategyGraphLayout (do not duplicate)
    if (meta) return;

    const leader = leaderRef.current;
    if (leader !== null && Date.now() <= leader.expires) {
      // Two-key sequence in flight (`g` is currently the only leader).
      if (event.key === "s") {
        event.preventDefault();
        leaderRef.current = null;
        router.push(strategyHref);
        return;
      }
      if (event.key === "c") {
        event.preventDefault();
        leaderRef.current = null;
        router.push(chatHref);
        return;
      }
      // Any other key cancels the leader.
      leaderRef.current = null;
    }

    switch (event.key) {
      case "r": {
        event.preventDefault();
        ctx.handleRelayout();
        return;
      }
      case "f": {
        event.preventDefault();
        void fitView({ padding: 0.3, duration: 300 });
        return;
      }
      case "+":
      case "=": {
        event.preventDefault();
        void zoomIn({ duration: 150 });
        return;
      }
      case "-": {
        event.preventDefault();
        void zoomOut({ duration: 150 });
        return;
      }
      case "e": {
        event.preventDefault();
        const id = ctx.selectedNodeIds[0];
        if (id == null) return;
        const step = ctx.editableSteps.find((s) => s.id === id);
        if (step != null) ctx.setSelectedStep(step);
        return;
      }
      case "c": {
        event.preventDefault();
        if (ctx.selectedNodeIds.length >= 2) {
          ctx.handleStartCombineFromSelection();
        }
        return;
      }
      case "o": {
        event.preventDefault();
        ctx.handleStartOrthologTransformFromSelection();
        return;
      }
      case "Backspace":
      case "Delete": {
        if (ctx.selectedNodeIds.length === 0) return;
        event.preventDefault();
        if (ctx.selectedNodeIds.length === 1) {
          ctx.requestDelete(ctx.selectedNodeIds[0]!);
        } else {
          ctx.requestDeleteMany(ctx.selectedNodeIds);
        }
        return;
      }
      case "?": {
        event.preventDefault();
        onToggleShortcutsOverlay();
        return;
      }
      case "Escape": {
        // If a sheet/dialog (editor, quick switcher, ...) is open, let it
        // handle Esc and close itself - never navigate out from under it.
        if (document.querySelector('[role="dialog"][data-state="open"]') != null) {
          return;
        }
        event.preventDefault();
        const onStepRoute = pathname.includes("/strategy/step/");
        // A deep-linked step route keeps the editor in the URL; Esc steps up
        // to the canvas. From the bare canvas, Esc returns to chat.
        if (ctx.selectedStep != null || onStepRoute) {
          ctx.setSelectedStep(null);
          if (onStepRoute) router.push(strategyHref);
          return;
        }
        router.push(chatHref);
        return;
      }
      case "g": {
        event.preventDefault();
        leaderRef.current = { key: "g", expires: Date.now() + LEADER_TIMEOUT_MS };
        return;
      }
      default:
        return;
    }
  };

  // Capture phase so Esc is observed before an open Radix sheet/dialog
  // tears itself down - otherwise we'd read stale "no editor open" state and
  // wrongly navigate away from the canvas.
  useEventListener("keydown", handleKeyDown, undefined, { capture: true });
}
