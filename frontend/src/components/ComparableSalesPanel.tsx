"use client";

import React, { useState } from "react";

interface ComparableSale {
  address: string;
  price: number;
  sale_date: string;
  sqft: number;
  price_per_sqft: number;
  distance_m: number;
  property_type: string;
  bedrooms?: number;
  year_built?: number;
  adjustment_factor: number;
}

interface ComparableSalesPanelProps {
  parcelId: string;
  comparables: ComparableSale[];
}

type SortKey = "address" | "price" | "sale_date" | "sqft" | "price_per_sqft" | "distance_m";
type SortOrder = "asc" | "desc";

export const ComparableSalesPanel: React.FC<ComparableSalesPanelProps> = ({
  parcelId,
  comparables,
}) => {
  const [sortKey, setSortKey] = useState<SortKey>("distance_m");
  const [sortOrder, setSortOrder] = useState<SortOrder>("asc");

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortOrder("asc");
    }
  };

  const sortedComparables = [...comparables].sort((a, b) => {
    let aValue: string | number = a[sortKey];
    let bValue: string | number = b[sortKey];

    if (sortKey === "sale_date") {
      aValue = new Date(a.sale_date).getTime();
      bValue = new Date(b.sale_date).getTime();
    }

    if (typeof aValue === "string" && typeof bValue === "string") {
      return sortOrder === "asc"
        ? aValue.localeCompare(bValue)
        : bValue.localeCompare(aValue);
    }

    if (typeof aValue === "number" && typeof bValue === "number") {
      return sortOrder === "asc" ? aValue - bValue : bValue - aValue;
    }

    return 0;
  });

  const avgPsf =
    comparables.length > 0
      ? comparables.reduce((sum, c) => sum + c.price_per_sqft, 0) / comparables.length
      : 0;

  const medianPrice =
    comparables.length > 0
      ? [...comparables]
          .sort((a, b) => a.price - b.price)[Math.floor(comparables.length / 2)]?.price || 0
      : 0;

  const priceRange = {
    low: Math.min(...comparables.map((c) => c.price)),
    high: Math.max(...comparables.map((c) => c.price)),
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat("en-CA", {
      style: "currency",
      currency: "CAD",
      maximumFractionDigits: 0,
    }).format(value);
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString("en-CA");
  };

  const getSortIndicator = (key: SortKey) => {
    if (sortKey !== key) return " \u21C5";
    return sortOrder === "asc" ? " \u2191" : " \u2193";
  };

  return (
    <div className="w-full bg-transparent rounded-lg">
      {comparables.length === 0 ? (
        <div className="text-center py-4 text-gray-500 text-[11px]">
          No comparable sales found in the search area.
        </div>
      ) : (
        <>
          <div className="mb-3 grid grid-cols-2 gap-2">
            <div className="bg-blue-500/10 border border-blue-500/20 p-2 rounded">
              <p className="text-[9px] font-semibold text-gray-500 uppercase">Avg $/SqFt</p>
              <p className="text-sm font-bold text-blue-400">${avgPsf.toFixed(0)}</p>
            </div>
            <div className="bg-green-500/10 border border-green-500/20 p-2 rounded">
              <p className="text-[9px] font-semibold text-gray-500 uppercase">Median Price</p>
              <p className="text-sm font-bold text-green-400">{formatCurrency(medianPrice)}</p>
            </div>
            <div className="bg-purple-500/10 border border-purple-500/20 p-2 rounded">
              <p className="text-[9px] font-semibold text-gray-500 uppercase">Low</p>
              <p className="text-sm font-bold text-purple-400">{formatCurrency(priceRange.low)}</p>
            </div>
            <div className="bg-orange-500/10 border border-orange-500/20 p-2 rounded">
              <p className="text-[9px] font-semibold text-gray-500 uppercase">High</p>
              <p className="text-sm font-bold text-orange-400">{formatCurrency(priceRange.high)}</p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="text-left p-1.5 cursor-pointer hover:text-white text-gray-400 font-semibold" onClick={() => handleSort("address")}>
                    Address{getSortIndicator("address")}
                  </th>
                  <th className="text-right p-1.5 cursor-pointer hover:text-white text-gray-400 font-semibold" onClick={() => handleSort("price")}>
                    Price{getSortIndicator("price")}
                  </th>
                  <th className="text-center p-1.5 cursor-pointer hover:text-white text-gray-400 font-semibold" onClick={() => handleSort("sale_date")}>
                    Date{getSortIndicator("sale_date")}
                  </th>
                  <th className="text-right p-1.5 cursor-pointer hover:text-white text-gray-400 font-semibold" onClick={() => handleSort("price_per_sqft")}>
                    PSF{getSortIndicator("price_per_sqft")}
                  </th>
                  <th className="text-right p-1.5 cursor-pointer hover:text-white text-gray-400 font-semibold" onClick={() => handleSort("distance_m")}>
                    Dist{getSortIndicator("distance_m")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {sortedComparables.map((comp, idx) => (
                  <tr
                    key={idx}
                    className="border-b border-gray-800 hover:bg-white/[0.03] transition-colors"
                  >
                    <td className="p-1.5 text-gray-300 font-medium truncate max-w-[120px]">{comp.address}</td>
                    <td className="p-1.5 text-right text-gray-300">{formatCurrency(comp.price)}</td>
                    <td className="p-1.5 text-center text-gray-500 text-[10px]">
                      {formatDate(comp.sale_date)}
                    </td>
                    <td className="p-1.5 text-right font-medium text-gray-300">
                      ${comp.price_per_sqft.toFixed(0)}
                    </td>
                    <td className="p-1.5 text-right">
                      <span
                        className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${
                          comp.distance_m < 300
                            ? "bg-green-500/20 text-green-400"
                            : comp.distance_m < 600
                              ? "bg-yellow-500/20 text-yellow-400"
                              : "bg-orange-500/20 text-orange-400"
                        }`}
                      >
                        {comp.distance_m.toLocaleString("en-CA")}m
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-3 pt-2 border-t border-gray-800">
            <div className="text-[10px] text-gray-500">
              Time-adjusted, distance-weighted analysis. Recent sales within 12 months within 1km radius.
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default ComparableSalesPanel;
