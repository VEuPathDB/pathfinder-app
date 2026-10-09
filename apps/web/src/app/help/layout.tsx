import { FrameLocationReporter } from "@/app/components/FrameLocationReporter";

export default function HelpLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <FrameLocationReporter />
      {children}
    </>
  );
}
