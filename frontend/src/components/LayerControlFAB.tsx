"use client";

import { Layers, X } from "lucide-react";

interface LayerControlFABProps {
  onClick: () => void;
  isOpen: boolean;
}

export default function LayerControlFAB({ onClick, isOpen }: LayerControlFABProps) {
  return (
    <button
      onClick={onClick}
      className="md:hidden fixed bottom-20 right-4 z-50 w-14 h-14 rounded-full bg-blue-600 hover:bg-blue-700 active:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 shadow-lg flex items-center justify-center text-white transition-all"
      aria-label={isOpen ? "Close layer controls" : "Open layer controls"}
      aria-expanded={isOpen}
    >
      {isOpen ? <X className="w-6 h-6" /> : <Layers className="w-6 h-6" />}
    </button>
  );
}
