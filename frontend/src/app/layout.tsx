import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "VanCity Lens — Bill 47 Engine",
  description: "Geospatial entitlement engine for Vancouver real estate investors",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, padding: 0, background: "#0a0a0a" }}>
        {children}
      </body>
    </html>
  );
}
