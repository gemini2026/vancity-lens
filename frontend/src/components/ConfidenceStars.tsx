import React from "react";

interface ConfidenceStarsProps {
  rating: number;
  maxStars?: number;
  size?: "sm" | "md" | "lg";
}

export const ConfidenceStars: React.FC<ConfidenceStarsProps> = ({
  rating,
  maxStars = 5,
  size = "md",
}) => {
  const clampedRating = Math.min(Math.max(rating, 0), maxStars);

  const sizeClasses = {
    sm: "text-sm",
    md: "text-lg",
    lg: "text-2xl",
  };

  const labelSizeClasses = {
    sm: "text-xs",
    md: "text-sm",
    lg: "text-base",
  };

  const stars = Array.from({ length: maxStars }, (_, i) => {
    const starIndex = i + 1;
    const isFilled = clampedRating >= starIndex;
    const isHalfFilled = clampedRating >= starIndex - 0.5 && clampedRating < starIndex;

    return (
      <span
        key={i}
        className={`${sizeClasses[size]} ${
          isFilled || isHalfFilled ? "text-yellow-400" : "text-gray-600"
        }`}
        aria-hidden="true"
      >
        {isFilled ? "★" : isHalfFilled ? "⭐" : "☆"}
      </span>
    );
  });

  return (
    <div className="flex items-center gap-2">
      <div
        className="flex gap-0.5"
        role="img"
        aria-label={`${clampedRating.toFixed(1)} out of ${maxStars} confidence stars`}
      >
        {stars}
      </div>
      <span className={`${labelSizeClasses[size]} text-gray-400`}>
        {clampedRating.toFixed(1)}/{maxStars}
      </span>
    </div>
  );
};

export default ConfidenceStars;
