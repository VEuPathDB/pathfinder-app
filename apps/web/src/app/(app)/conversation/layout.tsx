import { ChatShell } from "@/features/conversation/ChatShell";
import { StrategyPopstateFlush } from "@/features/strategy/hooks/StrategyPopstateFlush";

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <StrategyPopstateFlush />
      <ChatShell />
      {children}
    </>
  );
}
