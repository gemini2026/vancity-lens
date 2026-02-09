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
    if (sortKey !== key) return " ⇅";
    return sortOrder === "asc" ? " ↑" : " ↓";
  };

  return (
    <div className="w-full bg-white rounded-lg shadow-md p-6">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-800 mb-2">Comparable Sales Analysis</h2>
        <p className="text-sm text-gray-600">Parcel ID: {parcelId}</p>
      </div>

      {comparables.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          No comparable sales found in the search area.
        </div>
      ) : (
        <>
          <div className="mb-6 grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-blue-50 p-4 rounded">
              <p className="text-xs font-semibold text-gray-600 uppercase">Avg Price/SqFt</p>
              <p className="text-lg font-bold text-blue-600">${avgPsf.toFixed(2)}</p>
            </div>
            <div className="bg-green-50 p-4 rounded">
              <p className="text-xs font-semibold text-gray-600 uppercase">Median Price</p>
              <p className="text-lg font-bold text-green-600">{formatCurrency(medianPrice)}</p>
            </div>
            <div className="bg-purple-50 p-4 rounded">
              <p className="text-xs font-semibold text-gray-600 uppercase">Price Range Low</p>
              <p className="text-lg font-bold text-purple-600">{formatCurrency(priceRange.low)}</p>
            </div>
            <div className="bg-orange-50 p-4 rounded">
              <p className="text-xs font-semibold text-gray-600 uppercase">Price Range High</p>
              <p className="text-lg font-bold text-orange-600">{formatCurrency(priceRange.high)}</p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b-2 border-gray-300 bg-gray-50">
                  <th className="text-left p-3 cursor-pointer hover:bg-gray-100" onClick={() => handleSort("address")}>
                    Address {getSortIndicator("address")}
                  </th>
                  <th className="text-right p-3 cursor-pointer hover:bg-gray-100" onClick={() => handleSort("price")}>
                    Sale Price {getSortIndicator("price")}
                  </th>
                  <th className="text-center p-3 cursor-pointer hover:bg-gray-100" onClick={() => handleSort("sale_date")}>
                    Date {getSortIndicator("sale_date")}
                  </th>
                  <th className="text-right p-3 cursor-pointer hover:bg-gray-100" onClick={() => handleSort("sqft")}>
                    SqFt {getSortIndicator("sqft")}
                  </th>
                  <th className="text-right p-3 cursor-pointer hover:bg-gray-100" onClick={() => handleSort("price_per_sqft")}>
                    PSF {getSortIndicator("price_per_sqft")}
                  </th>
                  <th className="text-right p-3 cursor-pointer hover:bg-gray-100" onClick={() => handleSort("distance_m")}>
                    Distance {getSortIndicator("distance_m")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {sortedComparables.map((comp, idx) => (
                  <tr
                    key={idx}
                    className="border-b border-gray-200 hover:bg-gray-50 transition-colors"
                  >
                    <td className="p-3 text-gray-800 font-medium">{comp.address}</td>
                    <td className="p-3 text-right text-gray-700">{formatCurrency(comp.price)}</td>
                    <td className="p-3 text-center text-gray-600 text-xs">
                      {formatDate(comp.sale_date)}
                    </td>
                    <td className="p-3 text-right text-gray-600">
                      {comp.sqft.toLocaleString("en-CA")}
                    </td>
                    <td className="p-3 text-right font-medium text-gray-800">
                      ${comp.price_per_sqft.toFixed(2)}
                    </td>
                    <td className="p-3 text-right text-gray-600">
                      <span
                        className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${
                          comp.distance_m < 300
                            ? "bg-green-100 text-green-800"
                            : comp.distance_m < 600
                              ? "bg-yellow-100 text-yellow-800"
                              : "bg-orange-100 text-orange-800"
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

          <div className="mt-6 pt-6 border-t border-gray-200">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Adjustment Highlights</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="text-sm bg-blue-50 p-3 rounded">
                <span className="font-medium text-gray-700">Time Adjustments: </span>
                <span className="text-gray-600">Recent sales within 12 months preferred</span>
              </div>
              <div className="text-sm bg-green-50 p-3 rounded">
                <span className="font-medium text-gray-700">Location Adjustments: </span>
                <span className="text-gray-600">Proximity impacts comparable relevance</span>
              </div>
              <div className="text-sm bg-purple-50 p-3 rounded">
                <span className="font-medium text-gray-700">Size Adjustments: </span>
                <span className="text-gray-600">Property size reflected in PSF comparison</span>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default ComparableSalesPanel;
