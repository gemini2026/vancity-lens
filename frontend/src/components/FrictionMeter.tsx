import React from "react";

interface FrictionMeterProps {
  value: number;
  size?: "sm" | "md" | "lg";
}

export const FrictionMeter: React.FC<FrictionMeterProps> = ({ value, size = "md" }) => {
  const clampedValue = Math.min(Math.max(value, 0), 100);
  const percentage = (clampedValue / 100) * 100;

  const getColor = (val: number): string => {
    if (val <= 30) return "#22c55e";
    if (val <= 60) return "#eab308";
    return "#dc2626";
  };

  const getLabel = (val: number): string => {
    if (val <= 30) return "Low Friction";
    if (val <= 60) return "Medium Friction";
    return "High Friction";
  };

  const sizeClasses = {
    sm: "h-2",
    md: "h-3",
    lg: "h-4",
  };

  const labelSizeClasses = {
    sm: "text-xs",
    md: "text-sm",
    lg: "text-base",
  };

  const color = getColor(clampedValue);
  const label = getLabel(clampedValue);

  return (
    <div className="w-full">
      <div className="flex justify-between items-center mb-1">
        <label className={`${labelSizeClasses[size]} font-semibold text-gray-300`}>
          Friction Meter
        </label>
        <span
          className={`${labelSizeClasses[size]} font-bold text-gray-100`}
          title={`Friction score: ${clampedValue}`}
          aria-label={`Friction score: ${clampedValue} out of 100`}
        >
          {clampedValue}
        </span>
      </div>

      <div
        className={`${sizeClasses[size]} w-full bg-gray-700 rounded-full overflow-hidden`}
        role="progressbar"
        aria-label={`${label}: ${clampedValue}`}
        aria-valuenow={clampedValue}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{
            width: `${percentage}%`,
            backgroundColor: color,
          }}
        />
      </div>

      <div className="flex justify-between mt-1">
        <span className={`${labelSizeClasses[size]} text-gray-500`}>
          {label}
        </span>
        <div className="flex gap-2 text-xs text-gray-500">
          <span>Low</span>
          <span>High</span>
        </div>
      </div>
    </div>
  );
};

export default FrictionMeter;
