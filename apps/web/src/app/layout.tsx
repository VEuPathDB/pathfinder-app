import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "@/styles/globals.css";
import "streamdown/styles.css";
import { TelemetryErrorBoundary } from "@/lib/telemetry/ErrorBoundary";
import { Providers } from "./components/Providers";

// Every page requires auth + API data - nothing should be statically prerendered.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "PathFinder",
  description: "AI-powered search strategy builder for VEuPathDB",
  icons: {
    icon: "/favicon.svg",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${GeistSans.variable} ${GeistMono.variable}`}
    >
      <body className="h-full overflow-hidden bg-background text-foreground font-sans antialiased">
        <TelemetryErrorBoundary>
          <Providers>
            <main className="h-full">{children}</main>
          </Providers>
        </TelemetryErrorBoundary>
      </body>
    </html>
  );
}
