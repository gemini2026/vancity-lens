import React from "react";
import { FrictionMeter } from "./FrictionMeter";
import { ConfidenceStars } from "./ConfidenceStars";
import type { ParcelEntitlement } from "@/lib/types";

interface DueDiligencePopupProps {
  parcel: ParcelEntitlement;
}

export const DueDiligencePopup: React.FC<DueDiligencePopupProps> = ({ parcel }) => {
  const { validation, civic_address, pid } = parcel;

  if (!validation) {
    return (
      <div className="p-4 text-gray-400">
        <p>No validation data available</p>
      </div>
    );
  }

  const {
    confidence_stars = 1,
    friction_score = 0,
    deal_grade,
    deal_score,
    one_liner,
  } = validation;

  return (
    <div className="bg-gray-900 text-gray-100 p-4 rounded-lg space-y-4">
      {/* Header */}
      <div>
        <h3 className="text-base font-bold text-white">
          {civic_address || pid}
        </h3>
        <p className="text-xs text-gray-400 mt-1">{one_liner}</p>
      </div>

      {/* Grade and Score */}
      <div className="flex items-center justify-between gap-3 p-3 bg-gray-800 rounded-lg">
        <div>
          <p className="text-xs text-gray-500">Deal Grade</p>
          <p className="text-lg font-bold text-white">{deal_grade}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Score</p>
          <p className="text-lg font-bold text-white">{deal_score}/100</p>
        </div>
      </div>

      {/* Confidence Stars */}
      <div className="p-3 bg-gray-800 rounded-lg">
        <p className="text-xs text-gray-500 mb-2">Confidence Rating</p>
        <ConfidenceStars rating={confidence_stars} size="md" />
      </div>

      {/* Friction Meter */}
      <div className="p-3 bg-gray-800 rounded-lg">
        <p className="text-xs text-gray-500 mb-2">Entitlement Friction</p>
        <FrictionMeter value={friction_score} size="md" />
      </div>

      {/* Additional Details */}
      {validation.neighborhood && (
        <div className="p-3 bg-gray-800 rounded-lg">
          <p className="text-xs text-gray-500">Neighborhood</p>
          <p className="text-sm text-white mt-1">{validation.neighborhood}</p>
        </div>
      )}

      {/* Execution Difficulty */}
      {validation.execution_difficulty_score > 0 && (
        <div className="p-3 bg-gray-800 rounded-lg">
          <p className="text-xs text-gray-500 mb-2">Execution Difficulty</p>
          <div className="flex items-center gap-2">
            <div
              className={`inline-flex items-center justify-center w-8 h-8 rounded-full font-bold text-white ${
                validation.execution_difficulty_score >= 7
                  ? "bg-red-600"
                  : validation.execution_difficulty_score >= 4
                    ? "bg-yellow-600"
                    : "bg-green-600"
              }`}
            >
              {validation.execution_difficulty_score}
            </div>
            <span className="text-sm text-gray-300">/10</span>
          </div>
          {validation.execution_difficulty_factors.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-2">
              {validation.execution_difficulty_factors.map((factor, idx) => (
                <span
                  key={idx}
                  className="text-xs bg-gray-700 text-gray-300 px-2 py-1 rounded"
                >
                  {factor}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default DueDiligencePopup;
