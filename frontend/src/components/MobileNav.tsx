"use client";

import { useState } from "react";
import Link from "next/link";

interface MobileNavProps {
  activeTab: "map" | "intel" | "hoods" | "alerts";
  onTabChange: (tab: "map" | "intel" | "hoods" | "alerts") => void;
}

export default function MobileNav({ activeTab, onTabChange }: MobileNavProps) {
  const [isOpen, setIsOpen] = useState(false);

  const navItems = [
    { id: "map", label: "Map", icon: "📍" },
    { id: "intel", label: "Intelligence", icon: "🧠" },
    { id: "hoods", label: "Neighborhoods", icon: "🏢" },
    { id: "alerts", label: "Alerts", icon: "🔔" },
  ] as const;

  const handleNavClick = (tab: typeof navItems[number]["id"]) => {
    onTabChange(tab as "map" | "intel" | "hoods" | "alerts");
    setIsOpen(false);
  };

  return (
    <>
      {/* Hamburger Menu Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="md:hidden fixed top-4 left-4 z-40 p-2 rounded-lg bg-slate-800 border border-slate-700 hover:bg-slate-700 transition-colors"
        aria-label="Toggle navigation menu"
        aria-expanded={isOpen}
      >
        <div className="w-6 h-6 flex flex-col justify-center gap-1.5">
          <span
            className={`h-0.5 w-6 bg-gray-300 transition-all duration-300 ${
              isOpen ? "rotate-45 translate-y-2" : ""
            }`}
          />
          <span
            className={`h-0.5 w-6 bg-gray-300 transition-all duration-300 ${
              isOpen ? "opacity-0" : ""
            }`}
          />
          <span
            className={`h-0.5 w-6 bg-gray-300 transition-all duration-300 ${
              isOpen ? "-rotate-45 -translate-y-2" : ""
            }`}
          />
        </div>
      </button>

      {/* Overlay */}
      {isOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/50 z-30 transition-opacity duration-300"
          onClick={() => setIsOpen(false)}
          role="presentation"
        />
      )}

      {/* Slide-out Drawer */}
      <nav
        className={`md:hidden fixed left-0 top-0 h-screen w-64 bg-slate-900 border-r border-slate-700 z-40 transform transition-transform duration-300 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        role="navigation"
        aria-label="Mobile navigation menu"
      >
        {/* Close Button */}
        <button
          onClick={() => setIsOpen(false)}
          className="absolute top-4 right-4 p-2 rounded-lg hover:bg-slate-800 transition-colors"
          aria-label="Close navigation menu"
        >
          <span className="text-gray-400 hover:text-gray-200 text-2xl">✕</span>
        </button>

        {/* Nav Items */}
        <div className="pt-16 px-4 space-y-2">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => handleNavClick(item.id)}
              className={`w-full text-left px-4 py-3 rounded-lg transition-all duration-200 font-medium ${
                activeTab === item.id
                  ? "bg-blue-600 text-white border-l-4 border-blue-400"
                  : "text-gray-300 hover:bg-slate-800 hover:text-gray-100"
              }`}
              aria-current={activeTab === item.id ? "page" : undefined}
            >
              <span className="mr-3">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </div>
      </nav>
    </>
  );
}
