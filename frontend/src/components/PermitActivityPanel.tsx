import React, { useState } from "react";

interface BuildingPermit {
  permit_number: string;
  address: string;
  permit_type: "new_build" | "renovation" | "demolition";
  status: "applied" | "approved" | "issued" | "completed";
  project_value: number;
  units_proposed?: number;
  storeys?: number;
  sqft?: number;
  issued_date?: string;
  applicant?: string;
}

interface PermitActivityPanelProps {
  parcelId?: string;
  permits: BuildingPermit[];
  onPermitClick?: (permit: BuildingPermit) => void;
}

const getStatusBadgeColor = (status: string): string => {
  switch (status) {
    case "applied":
      return "bg-yellow-100 text-yellow-800";
    case "approved":
      return "bg-blue-100 text-blue-800";
    case "issued":
      return "bg-green-100 text-green-800";
    case "completed":
      return "bg-gray-100 text-gray-800";
    default:
      return "bg-gray-100 text-gray-800";
  }
};

const getPermitTypeLabel = (type: string): string => {
  switch (type) {
    case "new_build":
      return "New Building";
    case "renovation":
      return "Renovation";
    case "demolition":
      return "Demolition";
    default:
      return type;
  }
};

const getPermitTypeColor = (type: string): string => {
  switch (type) {
    case "new_build":
      return "text-blue-600";
    case "renovation":
      return "text-orange-600";
    case "demolition":
      return "text-red-600";
    default:
      return "text-gray-600";
  }
};

const formatCurrency = (value: number): string => {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

const PermitActivityPanel: React.FC<PermitActivityPanelProps> = ({
  parcelId,
  permits,
  onPermitClick,
}) => {
  const [filterType, setFilterType] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<string | null>(null);

  const pipelineUnits = permits
    .filter(
      (p) =>
        ["applied", "approved", "issued"].includes(p.status) &&
        p.units_proposed
    )
    .reduce((sum, p) => sum + (p.units_proposed || 0), 0);

  const supplyPressure = Math.min(
    100,
    (pipelineUnits / Math.max(1, pipelineUnits + 1)) * 100
  );

  const newBuildCount = permits.filter(
    (p) => p.permit_type === "new_build"
  ).length;

  const filteredPermits = permits.filter((p) => {
    if (filterType && p.permit_type !== filterType) return false;
    if (filterStatus && p.status !== filterStatus) return false;
    return true;
  });

  return (
    <div className="bg-white rounded-lg shadow-md p-6 max-w-2xl">
      <h2 className="text-xl font-bold mb-4">Building Permit Activity</h2>

      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-blue-50 rounded p-3">
          <div className="text-xs text-gray-600 mb-1">Total Permits</div>
          <div className="text-2xl font-bold text-blue-700">{permits.length}</div>
        </div>

        <div className="bg-green-50 rounded p-3">
          <div className="text-xs text-gray-600 mb-1">New Building</div>
          <div className="text-2xl font-bold text-green-700">{newBuildCount}</div>
        </div>

        <div className="bg-purple-50 rounded p-3">
          <div className="text-xs text-gray-600 mb-1">Pipeline Units</div>
          <div className="text-2xl font-bold text-purple-700">
            {pipelineUnits}
          </div>
        </div>

        <div className="bg-red-50 rounded p-3">
          <div className="text-xs text-gray-600 mb-1">Supply Pressure</div>
          <div className="text-2xl font-bold text-red-700">
            {Math.round(supplyPressure)}%
          </div>
        </div>
      </div>

      <div className="mb-6">
        <div className="text-sm font-semibold mb-2">Supply Pressure Gauge</div>
        <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
          <div
            className={`h-full transition-all ${
              supplyPressure < 33
                ? "bg-green-500"
                : supplyPressure < 66
                  ? "bg-yellow-500"
                  : "bg-red-500"
            }`}
            style={{ width: `${supplyPressure}%` }}
          />
        </div>
        <div className="text-xs text-gray-600 mt-1">
          {supplyPressure < 33
            ? "Low pressure"
            : supplyPressure < 66
              ? "Moderate pressure"
              : "High competitive pressure"}
        </div>
      </div>

      <div className="flex gap-3 mb-6">
        <div className="flex-1">
          <label className="text-xs font-semibold text-gray-700 block mb-1">
            Filter by Type
          </label>
          <select
            value={filterType || ""}
            onChange={(e) => setFilterType(e.target.value || null)}
            className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
          >
            <option value="">All Types</option>
            <option value="new_build">New Building</option>
            <option value="renovation">Renovation</option>
            <option value="demolition">Demolition</option>
          </select>
        </div>

        <div className="flex-1">
          <label className="text-xs font-semibold text-gray-700 block mb-1">
            Filter by Status
          </label>
          <select
            value={filterStatus || ""}
            onChange={(e) => setFilterStatus(e.target.value || null)}
            className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
          >
            <option value="">All Statuses</option>
            <option value="applied">Applied</option>
            <option value="approved">Approved</option>
            <option value="issued">Issued</option>
            <option value="completed">Completed</option>
          </select>
        </div>
      </div>

      <div className="space-y-2 max-h-96 overflow-y-auto">
        {filteredPermits.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            No permits match the selected filters
          </div>
        ) : (
          filteredPermits.map((permit) => (
            <div
              key={permit.permit_number}
              onClick={() => onPermitClick?.(permit)}
              className="p-3 border border-gray-200 rounded hover:bg-gray-50 cursor-pointer transition"
            >
              <div className="flex justify-between items-start mb-2">
                <div className="flex-1">
                  <div className="font-semibold text-sm text-gray-900">
                    {permit.address}
                  </div>
                  <div className={`text-xs font-medium ${getPermitTypeColor(permit.permit_type)}`}>
                    {getPermitTypeLabel(permit.permit_type)}
                  </div>
                </div>
                <span
                  className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusBadgeColor(permit.status)}`}
                >
                  {permit.status.charAt(0).toUpperCase() + permit.status.slice(1)}
                </span>
              </div>

              <div className="grid grid-cols-3 gap-2 text-xs text-gray-600">
                {permit.units_proposed !== undefined && (
                  <div>
                    <span className="font-semibold">Units:</span>{" "}
                    {permit.units_proposed}
                  </div>
                )}
                {permit.storeys !== undefined && (
                  <div>
                    <span className="font-semibold">Storeys:</span>{" "}
                    {permit.storeys}
                  </div>
                )}
                <div>
                  <span className="font-semibold">Value:</span>{" "}
                  {formatCurrency(permit.project_value)}
                </div>
              </div>

              {permit.issued_date && (
                <div className="text-xs text-gray-500 mt-2">
                  Issued: {new Date(permit.issued_date).toLocaleDateString()}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default PermitActivityPanel;
