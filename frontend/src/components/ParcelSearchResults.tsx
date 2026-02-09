"use client";

import { useState, useMemo } from "react";
import type { ReactNode } from "react";

export interface ParcelResult {
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

interface ParcelSearchResultsProps {
  results: ParcelResult[];
  onSelect: (parcel: ParcelResult) => void;
  isLoading: boolean;
  className?: string;
}

function MatchScoreIndicator({ score }: { score: number }): ReactNode {
  const percentage = Math.round(score * 100);
  let colorClass = "text-gray-500";

  if (percentage >= 80) {
    colorClass = "text-green-600";
  } else if (percentage >= 60) {
    colorClass = "text-blue-600";
  } else if (percentage >= 40) {
    colorClass = "text-yellow-600";
  } else {
    colorClass = "text-orange-600";
  }

  return (
    <div className="flex items-center gap-2">
      <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center">
        <span className={`text-xs font-semibold ${colorClass}`}>
          {percentage}%
        </span>
      </div>
    </div>
  );
}

function ResultSkeleton(): ReactNode {
  return (
    <div className="p-4 border-b border-gray-200 last:border-b-0 animate-pulse">
      <div className="h-4 bg-gray-300 rounded w-3/4 mb-2"></div>
      <div className="h-3 bg-gray-200 rounded w-1/2 mb-3"></div>
      <div className="flex justify-between items-center">
        <div className="h-3 bg-gray-200 rounded w-1/4"></div>
        <div className="h-3 bg-gray-200 rounded w-1/4"></div>
      </div>
    </div>
  );
}

function EmptyState(): ReactNode {
  return (
    <div className="p-8 text-center text-gray-500">
      <div className="mb-2 text-4xl">magnifying-glass</div>
      <p className="text-sm font-medium">No parcels found</p>
      <p className="text-xs mt-1">
        Try searching with a different address or PID
      </p>
    </div>
  );
}

export default function ParcelSearchResults({
  results,
  onSelect,
  isLoading,
  className = "",
}: ParcelSearchResultsProps): ReactNode {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const sortedResults = useMemo(() => {
    return [...results].sort((a, b) => b.match_score - a.match_score);
  }, [results]);

  if (isLoading) {
    return (
      <div
        className={`bg-white rounded-lg border border-gray-200 overflow-hidden ${className}`}
      >
        {[1, 2, 3].map((i) => (
          <ResultSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div
        className={`bg-white rounded-lg border border-gray-200 overflow-hidden ${className}`}
      >
        <EmptyState />
      </div>
    );
  }

  return (
    <div
      className={`bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm ${className}`}
      role="list"
    >
      {sortedResults.map((parcel) => {
        const isSelected = selectedId === parcel.parcel_id;

        return (
          <button
            key={parcel.parcel_id}
            onClick={() => {
              setSelectedId(parcel.parcel_id);
              onSelect(parcel);
            }}
            className={`w-full p-4 border-b border-gray-200 last:border-b-0 text-left transition-colors hover:bg-blue-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-0 ${
              isSelected ? "bg-blue-50" : ""
            }`}
            aria-pressed={isSelected}
          >
            <div className="flex justify-between items-start gap-3">
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-gray-900 truncate text-sm mb-1">
                  {parcel.civic_address}
                </h3>
                <p className="text-xs text-gray-600 mb-2">PID: {parcel.pid}</p>
                <div className="flex flex-wrap gap-2 text-xs">
                  <span className="inline-block px-2 py-1 bg-gray-100 text-gray-700 rounded">
                    {parcel.zoning}
                  </span>
                  <span className="inline-block px-2 py-1 bg-blue-100 text-blue-700 rounded">
                    {parcel.neighborhood}
                  </span>
                  <span className="inline-block px-2 py-1 bg-gray-100 text-gray-700 rounded">
                    {parcel.lot_area_sqm.toFixed(0)} m²
                  </span>
                </div>
              </div>
              <div className="flex-shrink-0">
                <MatchScoreIndicator score={parcel.match_score} />
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
