import { FrameLocationReporter } from "@/app/components/FrameLocationReporter";

export default function SharedLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <FrameLocationReporter />
      {children}
    </>
  );
}
