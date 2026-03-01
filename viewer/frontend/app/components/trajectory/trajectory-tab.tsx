import { Route } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "~/components/ui/empty";
import { LoadingDots } from "~/components/ui/loading-dots";
import type { IdeaPayload, TokenMetrics, TrajectoryIndex } from "~/lib/types";
import { EventTypeFilter } from "./event-type-filter";
import { VirtualStepList } from "./virtual-step-list";
import { StepDurationBar } from "./step-duration-bar";
import { MetricsSidebar } from "~/components/metrics/metrics-sidebar";
import { IdeaCard } from "~/components/idea/idea-card";
import { useState, useMemo } from "react";

interface Props {
  jobId: string;
  index: TrajectoryIndex | null;
  tokens: TokenMetrics | null;
  idea: IdeaPayload | null;
}

export function TrajectoryTab({ jobId, index, tokens, idea }: Props) {
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set());
  const [expandedStep, setExpandedStep] = useState<number | null>(null);

  const filteredSteps = useMemo(() => {
    if (!index) return [];
    if (activeFilters.size === 0) return index.steps;
    return index.steps.filter((s) => activeFilters.has(s.event_type));
  }, [index, activeFilters]);

  if (!index) {
    return (
      <Empty className="bg-card border">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <Route />
          </EmptyMedia>
          <EmptyTitle>No trajectory</EmptyTitle>
          <EmptyDescription>
            No ATIF trajectory found for this job.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  const toggleFilter = (eventType: string) => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(eventType)) {
        next.delete(eventType);
      } else {
        next.add(eventType);
      }
      return next;
    });
  };

  const clearFilters = () => setActiveFilters(new Set());

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-4">
      {/* Main timeline */}
      <div className="space-y-4">
        {/* Idea card */}
        {idea?.found && <IdeaCard idea={idea} />}

        {/* Timeline */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">
                Timeline ({filteredSteps.length}
                {activeFilters.size > 0 && ` / ${index.total_steps}`} steps)
              </CardTitle>
              {tokens?.cost?.estimated_cost_usd != null && (
                <span className="text-xs text-muted-foreground">
                  ${tokens.cost.estimated_cost_usd.toFixed(2)} total
                </span>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {/* Duration bar */}
            <StepDurationBar
              steps={index.steps}
              onStepClick={(idx) => setExpandedStep(idx)}
            />

            {/* Filters */}
            <EventTypeFilter
              steps={index.steps}
              activeFilters={activeFilters}
              onToggle={toggleFilter}
              onClearAll={clearFilters}
            />

            {/* Virtual step list */}
            <VirtualStepList
              jobId={jobId}
              steps={filteredSteps}
              expandedStep={expandedStep}
              onExpandStep={setExpandedStep}
            />
          </CardContent>
        </Card>
      </div>

      {/* Sidebar: metrics */}
      <div className="hidden xl:block">
        <MetricsSidebar tokens={tokens} />
      </div>
    </div>
  );
}
