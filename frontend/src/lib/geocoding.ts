export interface GeocodingResult {
  address: string;
  lat: number;
  lng: number;
  neighborhood?: string;
  postalCode?: string;
  confidence: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const CACHE_TTL = 60 * 60 * 1000;
const VANCOUVER_BOUNDS = {
  minLat: 49.0,
  maxLat: 49.4,
  minLng: -123.3,
  maxLng: -122.9,
};

interface CacheEntry {
  data: GeocodingResult[];
  timestamp: number;
}

const cache = new Map<string, CacheEntry>();

function isWithinVancouverBounds(lat: number, lng: number): boolean {
  return (
    lat >= VANCOUVER_BOUNDS.minLat &&
    lat <= VANCOUVER_BOUNDS.maxLat &&
    lng >= VANCOUVER_BOUNDS.minLng &&
    lng <= VANCOUVER_BOUNDS.maxLng
  );
}

function getCacheKey(query: string): string {
  return `geocode:${query.toLowerCase()}`;
}

function getCachedResults(cacheKey: string): GeocodingResult[] | null {
  const entry = cache.get(cacheKey);
  if (!entry) return null;

  const now = Date.now();
  if (now - entry.timestamp > CACHE_TTL) {
    cache.delete(cacheKey);
    return null;
  }

  return entry.data;
}

function setCachedResults(cacheKey: string, data: GeocodingResult[]): void {
  cache.set(cacheKey, {
    data,
    timestamp: Date.now(),
  });
}

export async function geocodeAddress(
  query: string
): Promise<GeocodingResult[]> {
  if (!query.trim()) {
    return [];
  }

  const cacheKey = getCacheKey(query);
  const cached = getCachedResults(cacheKey);
  if (cached) {
    return cached;
  }

  try {
    const response = await fetch(
      `${API_BASE}/api/v1/geocode?q=${encodeURIComponent(query)}`
    );
    if (!response.ok) {
      throw new Error(`Geocoding request failed: ${response.statusText}`);
    }

    const results: GeocodingResult[] = await response.json();
    const filteredResults = results.filter((r) =>
      isWithinVancouverBounds(r.lat, r.lng)
    );

    setCachedResults(cacheKey, filteredResults);
    return filteredResults;
  } catch (error) {
    console.error("Geocoding error:", error);
    return [];
  }
}

export async function reverseGeocode(
  lat: number,
  lng: number
): Promise<GeocodingResult> {
  if (!isWithinVancouverBounds(lat, lng)) {
    throw new Error("Coordinates outside Vancouver bounds");
  }

  const cacheKey = `reverse:${lat.toFixed(6)},${lng.toFixed(6)}`;
  const cached = getCachedResults(cacheKey);
  if (cached && cached.length > 0) {
    return cached[0];
  }

  try {
    const response = await fetch(
      `${API_BASE}/api/v1/reverse-geocode?lat=${lat}&lng=${lng}`
    );
    if (!response.ok) {
      throw new Error(`Reverse geocoding failed: ${response.statusText}`);
    }

    const result: GeocodingResult = await response.json();
    setCachedResults(cacheKey, [result]);
    return result;
  } catch (error) {
    console.error("Reverse geocoding error:", error);
    throw error;
  }
}
