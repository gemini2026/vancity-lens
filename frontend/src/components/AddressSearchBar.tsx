"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { geocodeAddress, reverseGeocode } from "@/lib/geocoding";
import type { GeocodingResult } from "@/lib/geocoding";

interface AddressSearchBarProps {
  onSelect: (result: GeocodingResult) => void;
  placeholder?: string;
  className?: string;
}

const RECENT_SEARCHES_KEY = "address_search_history";
const MAX_RECENT_SEARCHES = 10;

export default function AddressSearchBar({
  onSelect,
  placeholder = "Search address in Vancouver",
  className = "",
}: AddressSearchBarProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeocodingResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [recentSearches, setRecentSearches] = useState<GeocodingResult[]>([]);
  const debounceTimer = useRef<NodeJS.Timeout | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const stored = localStorage.getItem(RECENT_SEARCHES_KEY);
    if (stored) {
      try {
        setRecentSearches(JSON.parse(stored));
      } catch {
        setRecentSearches([]);
      }
    }
  }, []);

  const updateRecentSearches = useCallback((result: GeocodingResult) => {
    setRecentSearches((prev) => {
      const filtered = prev.filter(
        (r) => !(r.lat === result.lat && r.lng === result.lng)
      );
      const updated = [result, ...filtered].slice(0, MAX_RECENT_SEARCHES);
      localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(updated));
      return updated;
    });
  }, []);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setQuery(value);
      setActiveIndex(-1);

      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }

      if (!value.trim()) {
        setResults([]);
        setIsOpen(false);
        return;
      }

      setIsOpen(true);
      setLoading(true);

      debounceTimer.current = setTimeout(async () => {
        try {
          const res = await geocodeAddress(value);
          setResults(res);
        } catch (err) {
          console.error("Geocoding failed:", err);
          setResults([]);
        } finally {
          setLoading(false);
        }
      }, 300);
    },
    []
  );

  const handleSelectResult = useCallback(
    (result: GeocodingResult) => {
      setQuery(result.address);
      setIsOpen(false);
      setResults([]);
      updateRecentSearches(result);
      onSelect(result);
    },
    [onSelect, updateRecentSearches]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (!isOpen) {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          setIsOpen(true);
        }
        return;
      }

      const displayResults =
        results.length > 0 ? results : recentSearches;

      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setActiveIndex((prev) =>
            prev < displayResults.length - 1 ? prev + 1 : prev
          );
          break;
        case "ArrowUp":
          e.preventDefault();
          setActiveIndex((prev) => (prev > 0 ? prev - 1 : -1));
          break;
        case "Enter":
          e.preventDefault();
          if (activeIndex >= 0 && displayResults[activeIndex]) {
            handleSelectResult(displayResults[activeIndex]);
          }
          break;
        case "Escape":
          e.preventDefault();
          setIsOpen(false);
          setActiveIndex(-1);
          break;
        default:
          break;
      }
    },
    [isOpen, results, recentSearches, activeIndex, handleSelectResult]
  );

  const handleClear = useCallback(() => {
    setQuery("");
    setResults([]);
    setIsOpen(false);
    setActiveIndex(-1);
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () =>
      document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const displayResults =
    results.length > 0 ? results : isOpen && query === "" ? recentSearches : [];

  return (
    <div
      className={`relative w-full max-w-md ${className}`}
      role="combobox"
      aria-expanded={isOpen}
      aria-haspopup="listbox"
    >
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (query === "") setIsOpen(true);
          }}
          placeholder={placeholder}
          className="w-full px-4 py-2 pr-10 bg-[var(--color-surface-secondary)] text-[var(--color-foreground)] placeholder-[var(--color-foreground-muted)] border border-[var(--color-border)] rounded-lg focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/40 focus:shadow-[0_0_12px_rgba(59,130,246,0.15)]"
          aria-autocomplete="list"
          aria-controls="address-dropdown"
          aria-activedescendant={
            activeIndex >= 0 ? `result-${activeIndex}` : ""
          }
        />
        {loading && (
          <div className="absolute right-3 top-1/2 transform -translate-y-1/2">
            <div className="w-4 h-4 border-2 border-slate-500 border-t-blue-500 rounded-full animate-spin" />
          </div>
        )}
        {query && !loading && (
          <button
            onClick={handleClear}
            className="absolute right-3 top-1/2 transform -translate-y-1/2 text-slate-400 hover:text-slate-200 transition"
            aria-label="Clear search"
          >
            ✕
          </button>
        )}
      </div>

      {isOpen && displayResults.length > 0 && (
        <div
          ref={dropdownRef}
          id="address-dropdown"
          role="listbox"
          className="absolute top-full left-0 right-0 mt-1 bg-[var(--color-card)] border border-[var(--color-border)] rounded-lg shadow-lg z-50 max-h-64 overflow-y-auto"
        >
          {displayResults.map((result, index) => (
            <div
              key={`${result.lat}-${result.lng}`}
              id={`result-${index}`}
              role="option"
              aria-selected={activeIndex === index}
              onClick={() => handleSelectResult(result)}
              className={`px-4 py-3 cursor-pointer border-b border-slate-700 last:border-b-0 transition ${
                activeIndex === index
                  ? "bg-blue-600 text-white"
                  : "hover:bg-slate-700 text-slate-100"
              }`}
            >
              <div className="font-medium">{result.address}</div>
              {(result.neighborhood || result.postal_code) && (
                <div className="text-xs text-slate-400 mt-1">
                  {result.neighborhood && <span>{result.neighborhood}</span>}
                  {result.neighborhood && result.postal_code && (
                    <span> · </span>
                  )}
                  {result.postal_code && <span>{result.postal_code}</span>}
                </div>
              )}
              {result.confidence && (
                <div className="text-xs text-slate-500 mt-1">
                  Confidence: {Math.round(result.confidence * 100)}%
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
