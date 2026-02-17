"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { useAddressSearch } from "@/hooks/useAddressSearch";
import type { AddressSearchResult } from "@/hooks/useAddressSearch";

interface AddressAutocompleteProps {
  onSelect: (result: AddressSearchResult) => void;
  placeholder?: string;
  className?: string;
}

/**
 * Address autocomplete component with dropdown UI and keyboard navigation.
 * Searches parcels as user types (min 3 characters).
 */
export default function AddressAutocomplete({
  onSelect,
  placeholder = "Search address in Vancouver",
  className = "",
}: AddressAutocompleteProps) {
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Use the search hook
  const { results, loading, error } = useAddressSearch(query, 10);

  // Close dropdown when clicking outside
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
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Handle input change
  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setQuery(value);
      setActiveIndex(-1);

      // Open dropdown if query is long enough
      if (value.trim().length >= 3) {
        setIsOpen(true);
      } else {
        setIsOpen(false);
      }
    },
    []
  );

  // Handle selecting a result
  const handleSelectResult = useCallback(
    (result: AddressSearchResult) => {
      setQuery(result.civic_address);
      setIsOpen(false);
      setActiveIndex(-1);
      onSelect(result);
    },
    [onSelect]
  );

  // Handle keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (!isOpen || results.length === 0) {
        if (e.key === "ArrowDown" && results.length > 0) {
          e.preventDefault();
          setIsOpen(true);
        }
        return;
      }

      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setActiveIndex((prev) =>
            prev < results.length - 1 ? prev + 1 : prev
          );
          break;
        case "ArrowUp":
          e.preventDefault();
          setActiveIndex((prev) => (prev > 0 ? prev - 1 : -1));
          break;
        case "Enter":
          e.preventDefault();
          if (activeIndex >= 0 && results[activeIndex]) {
            handleSelectResult(results[activeIndex]);
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
    [isOpen, results, activeIndex, handleSelectResult]
  );

  // Handle clear button
  const handleClear = useCallback(() => {
    setQuery("");
    setIsOpen(false);
    setActiveIndex(-1);
    inputRef.current?.focus();
  }, []);

  // Show dropdown content
  const showDropdown = isOpen && query.trim().length >= 3;

  return (
    <div
      className={`relative w-full ${className}`}
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
            if (query.trim().length >= 3) setIsOpen(true);
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
            <div className="w-4 h-4 border-2 border-[var(--color-foreground-muted)] border-t-blue-500 rounded-full animate-spin" />
          </div>
        )}
        {query && !loading && (
          <button
            onClick={handleClear}
            className="absolute right-3 top-1/2 transform -translate-y-1/2 text-[var(--color-foreground-muted)] hover:text-[var(--color-foreground)] transition"
            aria-label="Clear search"
          >
            ✕
          </button>
        )}
      </div>

      {showDropdown && (
        <div
          ref={dropdownRef}
          id="address-dropdown"
          role="listbox"
          className="absolute top-full left-0 right-0 mt-1 bg-[var(--color-card)] border border-[var(--color-border)] rounded-lg shadow-lg z-50 max-h-80 overflow-y-auto"
        >
          {loading && results.length === 0 && (
            <div className="px-4 py-3 text-[var(--color-foreground-muted)] text-sm">
              Loading suggestions...
            </div>
          )}

          {!loading && error && (
            <div className="px-4 py-3 text-[var(--color-foreground-muted)] text-sm">
              {error}
            </div>
          )}

          {!loading && !error && results.length === 0 && (
            <div className="px-4 py-3 text-[var(--color-foreground-muted)] text-sm">
              No addresses found
            </div>
          )}

          {results.length > 0 &&
            results.map((result, index) => (
              <div
                key={`${result.pid}-${index}`}
                id={`result-${index}`}
                role="option"
                aria-selected={activeIndex === index}
                onClick={() => handleSelectResult(result)}
                className={`px-4 py-3 cursor-pointer border-b border-[var(--color-border)] last:border-b-0 transition ${
                  activeIndex === index
                    ? "bg-blue-600 text-white"
                    : "hover:bg-[var(--color-surface-secondary)] text-[var(--color-foreground)]"
                }`}
              >
                <div className="font-medium">{result.civic_address}</div>
                {result.neighborhood && (
                  <div
                    className={`text-xs mt-1 ${
                      activeIndex === index
                        ? "text-blue-100"
                        : "text-[var(--color-foreground-muted)]"
                    }`}
                  >
                    {result.neighborhood}
                    {result.zoning && ` · ${result.zoning}`}
                  </div>
                )}
                {result.pid && (
                  <div
                    className={`text-xs mt-0.5 ${
                      activeIndex === index
                        ? "text-blue-200"
                        : "text-[var(--color-foreground-muted)]"
                    }`}
                  >
                    PID: {result.pid}
                  </div>
                )}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
