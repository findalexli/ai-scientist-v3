import { useState } from "react";

import type { StepSummary } from "~/lib/types";

interface Props {
  steps: StepSummary[];
  onStepClick: (index: number) => void;
}

function formatMs(ms: number): string {
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const rem = seconds % 60;
  return `${minutes}m ${rem.toFixed(0)}s`;
}

function getBarColor(index: number): string {
  const colors = [
    "var(--color-neutral-400, #9ca3af)",
    "var(--color-neutral-500, #6b7280)",
    "var(--color-neutral-600, #4b5563)",
    "var(--color-neutral-700, #374151)",
  ];
  const position = index % 6;
  const colorIndex = position <= 3 ? position : 6 - position;
  return colors[colorIndex];
}

export function StepDurationBar({ steps, onStepClick }: Props) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [hoverPosition, setHoverPosition] = useState(0);

  if (steps.length < 2) return null;

  // Calculate durations between consecutive steps
  const durations = steps.map((step, idx) => {
    if (idx === 0 || !step.timestamp || !steps[idx - 1].timestamp) return 0;
    return Math.max(
      0,
      new Date(step.timestamp).getTime() -
        new Date(steps[idx - 1].timestamp!).getTime()
    );
  });

  const totalMs = durations.reduce((sum, d) => sum + d, 0);
  if (totalMs === 0) return null;

  const widths = durations.map((d) => (d / totalMs) * 100);

  // Cumulative widths for tooltip positioning
  let cumulative = 0;
  const cumulativeWidths = widths.map((w) => {
    const pos = cumulative;
    cumulative += w;
    return pos;
  });

  return (
    <div className="mb-4">
      <div className="relative">
        {hoveredIndex !== null && (
          <div
            className="absolute bottom-full mb-2 z-10 -translate-x-1/2 pointer-events-none"
            style={{ left: `${hoverPosition}%` }}
          >
            <div className="bg-popover border border-border rounded-md shadow-md px-3 py-2 whitespace-nowrap text-xs">
              <div className="font-medium">Step #{steps[hoveredIndex].step_id}</div>
              <div className="text-muted-foreground">
                Duration: {formatMs(durations[hoveredIndex])}
              </div>
            </div>
          </div>
        )}
        <div className="flex h-5 overflow-hidden rounded-sm">
          {steps.map((step, idx) => {
            if (durations[idx] === 0) return null;
            const w = widths[idx];
            const isOtherHovered = hoveredIndex !== null && hoveredIndex !== idx;
            const center = cumulativeWidths[idx] + w / 2;

            return (
              <div
                key={step.step_id}
                className="transition-opacity duration-150 cursor-pointer"
                style={{
                  width: `${w}%`,
                  backgroundColor: getBarColor(idx),
                  opacity: isOtherHovered ? 0.3 : 1,
                }}
                onMouseEnter={() => {
                  setHoveredIndex(idx);
                  setHoverPosition(center);
                }}
                onMouseLeave={() => setHoveredIndex(null)}
                onClick={() => onStepClick(step.step_id)}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}
