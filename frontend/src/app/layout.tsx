import type { Metadata } from "next";
import { ThemeProvider } from "@/lib/theme-context";
import "@/styles/dark-mode.css";

export const metadata: Metadata = {
  title: "VanCity Lens — Bill 47 Engine",
  description: "Geospatial entitlement engine for Vancouver real estate investors",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body style={{ margin: 0, padding: 0 }}>
        <ThemeProvider>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
