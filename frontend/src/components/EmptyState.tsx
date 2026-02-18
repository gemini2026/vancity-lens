'use client';

import React from 'react';

export interface EmptyStateProps {
  icon: React.ReactNode;
  heading: string;
  description: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  suggestions?: string[];
  onSuggestionClick?: (suggestion: string) => void;
  className?: string;
}

export function EmptyState({
  icon,
  heading,
  description,
  action,
  suggestions = [],
  onSuggestionClick,
  className = '',
}: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center justify-center py-12 px-4 text-center ${className}`}>
      {/* Icon */}
      <div className="mb-6 text-gray-400 dark:text-gray-600">
        {icon}
      </div>

      {/* Heading */}
      <h3 className="text-lg font-semibold text-[var(--color-foreground)] mb-2">
        {heading}
      </h3>

      {/* Description */}
      <p className="text-sm text-[var(--color-foreground-secondary)] max-w-md mb-6">
        {description}
      </p>

      {/* Suggestions */}
      {suggestions.length > 0 && (
        <div className="flex flex-col gap-2 w-full max-w-md">
          <p className="text-xs text-[var(--color-foreground-muted)] mb-2">
            Try asking:
          </p>
          {suggestions.map((suggestion, index) => (
            <button
              key={index}
              onClick={() => onSuggestionClick?.(suggestion)}
              className="text-left px-4 py-2 text-sm rounded-lg border border-[var(--color-border)]
                         hover:bg-[var(--color-surface)] transition-colors
                         text-[var(--color-foreground-secondary)]"
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}

      {/* Action Button */}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700
                     transition-colors font-medium text-sm"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
