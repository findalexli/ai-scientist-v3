import { useMemo } from "react";

import { Badge } from "~/components/ui/badge";
import { EVENT_TYPES, getEventTypeConfig } from "~/lib/event-types";
import type { StepSummary } from "~/lib/types";

interface Props {
  steps: StepSummary[];
  activeFilters: Set<string>;
  onToggle: (eventType: string) => void;
  onClearAll?: () => void;
}

export function EventTypeFilter({ steps, activeFilters, onToggle, onClearAll }: Props) {
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const s of steps) {
      c[s.event_type] = (c[s.event_type] ?? 0) + 1;
    }
    return c;
  }, [steps]);

  const types = useMemo(() => {
    const order = Object.keys(EVENT_TYPES);
    const present = new Set(Object.keys(counts));
    return order.filter((t) => present.has(t));
  }, [counts]);

  if (types.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5 mb-4">
      {activeFilters.size > 0 && (
        <Badge
          variant="outline"
          className="cursor-pointer text-xs"
          onClick={onClearAll}
        >
          Clear filters
        </Badge>
      )}
      {types.map((type) => {
        const cfg = getEventTypeConfig(type);
        const isActive = activeFilters.has(type);
        return (
          <button
            key={type}
            onClick={() => onToggle(type)}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium transition-all border"
            style={{
              backgroundColor: isActive ? `${cfg.color}30` : "transparent",
              borderColor: isActive ? cfg.color : "var(--border)",
              color: isActive ? cfg.color : "var(--muted-foreground)",
            }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: cfg.color }}
            />
            {cfg.label}
            <span className="opacity-60">({counts[type] ?? 0})</span>
          </button>
        );
      })}
    </div>
  );
}
