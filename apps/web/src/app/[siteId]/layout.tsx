import { SystemReadyGate } from "@/app/components/SystemReadyGate";

export default async function SiteLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ siteId: string }>;
}) {
  const { siteId } = await params;
  return <SystemReadyGate siteId={siteId}>{children}</SystemReadyGate>;
}
