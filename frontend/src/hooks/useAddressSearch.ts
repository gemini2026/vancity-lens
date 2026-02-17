import { useState, useEffect } from "react";
import { getApiBase } from "@/lib/api-base";

const API_BASE = getApiBase();

export interface AddressSearchResult {
  parcel_id: string;
  pid: string;
  civic_address: string;
  lat: number;
  lng: number;
  lot_area_sqm: number;
  zoning: string;
  neighborhood: string;
  match_score: number;
}

interface SearchResponse {
  query: string;
  limit: number;
  count: number;
  disambiguation: boolean;
  results: AddressSearchResult[];
}

interface UseAddressSearchResult {
  results: AddressSearchResult[];
  loading: boolean;
  error: string | null;
}

/**
 * Hook for searching parcels by address with automatic debouncing.
 * Only triggers search when query is 3+ characters.
 *
 * @param query - The search query string
 * @param limit - Maximum number of results to return (default: 10)
 * @returns Object containing results, loading state, and error
 */
export function useAddressSearch(
  query: string,
  limit: number = 10
): UseAddressSearchResult {
  const [results, setResults] = useState<AddressSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Don't search if query is too short
    if (!query || query.trim().length < 3) {
      setResults([]);
      setError(null);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    let timeoutId: NodeJS.Timeout;

    const performSearch = async () => {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch(
          `${API_BASE}/api/v1/parcels/search?q=${encodeURIComponent(
            query
          )}&limit=${limit}`,
          { signal: controller.signal }
        );

        if (!response.ok) {
          if (response.status === 404) {
            // No results found
            setResults([]);
            setError("No addresses found");
          } else {
            throw new Error(`Search failed: ${response.statusText}`);
          }
        } else {
          const data: SearchResponse = await response.json();
          setResults(data.results || []);
        }
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          // Request was cancelled, ignore
          return;
        }
        console.error("Address search error:", err);
        setError(err instanceof Error ? err.message : "Search failed");
        setResults([]);
      } finally {
        setLoading(false);
      }
    };

    // Debounce the search by 300ms
    timeoutId = setTimeout(performSearch, 300);

    return () => {
      clearTimeout(timeoutId);
      controller.abort();
    };
  }, [query, limit]);

  return { results, loading, error };
}
