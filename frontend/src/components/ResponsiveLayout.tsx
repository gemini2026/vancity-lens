"use client";

import React, { ReactNode } from "react";

interface ResponsiveLayoutProps {
  children: ReactNode;
  sidebar?: ReactNode;
  activeTab?: "map" | "intel" | "hoods" | "alerts";
}

export default function ResponsiveLayout({
  children,
  sidebar,
  activeTab,
}: ResponsiveLayoutProps) {
  return (
    <div className="flex flex-col h-screen w-screen bg-slate-950">
      {/* Desktop Layout: Sidebar + Main Content */}
      <div className="hidden lg:flex flex-1 overflow-hidden">
        {/* Desktop Sidebar */}
        {sidebar && (
          <aside className="w-64 bg-slate-900 border-r border-slate-700 overflow-y-auto">
            {sidebar}
          </aside>
        )}

        {/* Desktop Main Content */}
        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </div>

      {/* Tablet Layout: Collapsible Sidebar + Full-width Main */}
      <div className="hidden md:flex lg:hidden flex-1 overflow-hidden">
        <main className="flex-1 overflow-auto w-full">
          {children}
        </main>
      </div>

      {/* Mobile Layout: Full-screen Content with Bottom Tab Navigation */}
      <div className="md:hidden flex flex-col flex-1 overflow-hidden">
        <main className="flex-1 overflow-auto relative w-full">
          {children}
        </main>
      </div>
    </div>
  );
}
