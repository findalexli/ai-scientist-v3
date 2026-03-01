import { useVirtualizer } from "@tanstack/react-virtual";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useCallback, useEffect, useRef } from "react";

import { Badge } from "~/components/ui/badge";
import { LoadingDots } from "~/components/ui/loading-dots";
import { ScrollArea } from "~/components/ui/scroll-area";
import { fetchStepDetail } from "~/lib/api";
import { getEventTypeConfig } from "~/lib/event-types";
import type { StepSummary } from "~/lib/types";
import { StepContent } from "./step-content";

interface Props {
  jobId: string;
  steps: StepSummary[];
  expandedStep: number | null;
  onExpandStep: (stepId: number | null) => void;
}

function formatDuration(
  prev: string | null,
  current: string | null
): string | null {
  if (!prev || !current) return null;
  const ms = new Date(current).getTime() - new Date(prev).getTime();
  if (ms < 0) return null;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${(s % 60).toFixed(0)}s`;
}

export function VirtualStepList({
  jobId,
  steps,
  expandedStep,
  onExpandStep,
}: Props) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: steps.length,
    getScrollElement: () => parentRef.current,
    estimateSize: (index) =>
      steps[index].step_id === expandedStep ? 400 : 44,
    overscan: 10,
  });

  // Scroll to expanded step
  useEffect(() => {
    if (expandedStep !== null) {
      const idx = steps.findIndex((s) => s.step_id === expandedStep);
      if (idx >= 0) {
        virtualizer.scrollToIndex(idx, { align: "start" });
      }
    }
  }, [expandedStep, steps, virtualizer]);

  return (
    <div
      ref={parentRef}
      className="overflow-auto"
      style={{ maxHeight: "70vh" }}
    >
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: "100%",
          position: "relative",
        }}
      >
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const step = steps[virtualRow.index];
          const prevStep =
            virtualRow.index > 0 ? steps[virtualRow.index - 1] : null;
          const isExpanded = step.step_id === expandedStep;

          return (
            <div
              key={step.step_id}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                transform: `translateY(${virtualRow.start}px)`,
              }}
              ref={virtualizer.measureElement}
              data-index={virtualRow.index}
            >
              <StepRow
                jobId={jobId}
                step={step}
                prevTimestamp={prevStep?.timestamp ?? null}
                isExpanded={isExpanded}
                onToggle={() =>
                  onExpandStep(isExpanded ? null : step.step_id)
                }
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function StepRow({
  jobId,
  step,
  prevTimestamp,
  isExpanded,
  onToggle,
}: {
  jobId: string;
  step: StepSummary;
  prevTimestamp: string | null;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const cfg = getEventTypeConfig(step.event_type);
  const duration = formatDuration(prevTimestamp, step.timestamp);

  return (
    <div className="border-b border-border/50">
      {/* Trigger */}
      <button
        onClick={onToggle}
        className={`w-full text-left px-3 py-2.5 flex items-center gap-2 hover:bg-muted/30 transition-colors ${
          isExpanded ? "bg-muted/20" : ""
        }`}
      >
        <ChevronRight
          className={`h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform ${
            isExpanded ? "rotate-90" : ""
          }`}
        />
        <span className="text-xs text-muted-foreground shrink-0 w-8 font-mono">
          #{step.step_id}
        </span>
        <span
          className="text-xs font-medium shrink-0"
          style={{ color: cfg.color }}
        >
          {step.source}
        </span>
        <Badge
          variant="outline"
          className="text-[10px] px-1.5 py-0 shrink-0"
          style={{
            borderColor: `${cfg.color}40`,
            color: cfg.color,
            backgroundColor: `${cfg.color}10`,
          }}
        >
          {cfg.label}
        </Badge>
        {step.tool_names.length > 0 && (
          <span className="text-xs text-muted-foreground shrink-0">
            {step.tool_names[0]}
            {step.tool_names.length > 1 && ` +${step.tool_names.length - 1}`}
          </span>
        )}
        <span className="text-xs text-muted-foreground truncate min-w-0 flex-1">
          {step.summary}
        </span>
        {duration && (
          <Badge variant="secondary" className="text-[10px] font-normal shrink-0">
            +{duration}
          </Badge>
        )}
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="px-3 pb-3 pl-12">
          <StepDetailLoader jobId={jobId} stepId={step.step_id} />
        </div>
      )}
    </div>
  );
}

function StepDetailLoader({
  jobId,
  stepId,
}: {
  jobId: string;
  stepId: number;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["step-detail", jobId, stepId],
    queryFn: () => fetchStepDetail(jobId, stepId),
    staleTime: Infinity, // Step content is immutable
  });

  if (isLoading) {
    return (
      <div className="py-4">
        <LoadingDots />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="py-4 text-xs text-destructive">
        Failed to load step content.
      </div>
    );
  }

  return <StepContent step={data} jobId={jobId} />;
}
