"use client";

import { useEffect, useState } from "react";
import { Sun, Moon, Monitor } from "lucide-react";
import { useTheme } from "@/lib/theme-context";
import { cn } from "@/lib/utils";

export default function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);
  if (!mounted) return null;

  const handleClick = () => {
    if (theme === "light") setTheme("dark");
    else if (theme === "dark") setTheme("system");
    else setTheme("light");
  };

  const Icon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;
  const label = theme === "light" ? "Light" : theme === "dark" ? "Dark" : "System";

  return (
    <button
      onClick={handleClick}
      aria-label={`Theme: ${label}`}
      title={label}
      className={cn(
        "p-2 rounded-lg transition-colors",
        "bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-100",
        "hover:bg-gray-300 dark:hover:bg-gray-600",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-brand",
        className
      )}
    >
      <Icon className="w-5 h-5" />
    </button>
  );
}
