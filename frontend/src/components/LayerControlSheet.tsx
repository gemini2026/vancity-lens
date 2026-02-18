"use client";

interface LayerControl {
  id: string;
  label: string;
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  color?: string;
}

interface LayerControlSheetProps {
  isOpen: boolean;
  onClose: () => void;
  controls: LayerControl[];
}

export default function LayerControlSheet({ isOpen, onClose, controls }: LayerControlSheetProps) {
  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="md:hidden fixed inset-0 bg-black/50 z-40"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Bottom Sheet */}
      <div className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-[var(--color-panel)] backdrop-blur-md rounded-t-2xl max-h-[70vh] overflow-y-auto border-t border-[var(--color-panel-border)] shadow-2xl">
        {/* Swipe handle */}
        <div className="flex justify-center py-3">
          <div className="w-12 h-1 rounded-full bg-[var(--color-foreground-muted)]/30" />
        </div>

        {/* Header */}
        <div className="px-6 pb-4 border-b border-[var(--color-panel-border)]">
          <h2 className="text-lg font-bold text-[var(--color-foreground)]">Map Layers</h2>
        </div>

        {/* Controls list */}
        <div className="px-6 py-4 space-y-3">
          {controls.map((control) => (
            <label
              key={control.id}
              className="flex items-center justify-between py-3 cursor-pointer touch-target"
            >
              <div className="flex items-center gap-3">
                {control.color && (
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: control.color }}
                  />
                )}
                <span className="text-[var(--color-foreground)] font-medium">
                  {control.label}
                </span>
              </div>
              <input
                type="checkbox"
                checked={control.enabled}
                onChange={(e) => control.onChange(e.target.checked)}
                className="w-5 h-5 rounded border-2 border-[var(--color-panel-border)] bg-[var(--color-surface)] checked:bg-blue-600 checked:border-blue-600 cursor-pointer"
              />
            </label>
          ))}
        </div>

        {/* Done button */}
        <div className="px-6 pb-6">
          <button
            onClick={onClose}
            className="w-full py-3 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold transition-colors touch-target"
          >
            Done
          </button>
        </div>
      </div>
    </>
  );
}
