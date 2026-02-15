import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { ThemeProvider } from "@/lib/theme-context";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "VanCity Lens — Bill 47 Engine",
  description: "Geospatial entitlement engine for Vancouver real estate investors",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <body className="font-sans bg-surface text-foreground antialiased">
        {/* Runtime env injection — placeholder replaced by entrypoint.sh at container start.
            Placed in <body> (not <head>) because Next.js 15 App Router strips custom <head> children.
            Value is a build-time constant (not user input), safe for inline script. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `window.__ENV__={MAPBOX_TOKEN:"${process.env.NEXT_PUBLIC_MAPBOX_TOKEN || ""}"}`,
          }}
        />
        <ThemeProvider>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
