import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Clock,
  DollarSign,
  ExternalLink,
  FileText,
  Layers,
  Route,
} from "lucide-react";
import { useState } from "react";
import { useHotkeys } from "react-hotkeys-hook";
import { Link, useNavigate, useParams } from "react-router";

import { Badge } from "~/components/ui/badge";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "~/components/ui/breadcrumb";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { LoadingDots } from "~/components/ui/loading-dots";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs";
import {
  fetchJobMeta,
  fetchSubmissions,
  fetchTokenMetrics,
  fetchTrajectoryIndex,
  fetchIdea,
} from "~/lib/api";
import type { JobMeta, TokenMetrics, TrajectoryIndex } from "~/lib/types";

// Lazy-loaded tab content
import { SubmissionsTab } from "~/components/submissions/submissions-tab";
import { TrajectoryTab } from "~/components/trajectory/trajectory-tab";

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "-";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, "default" | "secondary" | "outline" | "destructive"> = {
    running: "default",
    completed: "secondary",
    idle: "outline",
    unknown: "outline",
  };
  return (
    <Badge variant={variants[status] ?? "outline"} className="text-xs">
      {status}
    </Badge>
  );
}

export default function JobPage() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("submissions");

  useHotkeys("escape", () => navigate("/"), { enableOnFormTags: false });

  const { data: meta, isLoading: metaLoading } = useQuery({
    queryKey: ["job-meta", jobId],
    queryFn: () => fetchJobMeta(jobId!),
    enabled: !!jobId,
  });

  const { data: tokens } = useQuery({
    queryKey: ["job-tokens", jobId],
    queryFn: () => fetchTokenMetrics(jobId!),
    enabled: !!jobId,
  });

  const { data: submissionsData } = useQuery({
    queryKey: ["job-submissions", jobId],
    queryFn: () => fetchSubmissions(jobId!),
    enabled: !!jobId,
  });

  const { data: trajectoryIndex } = useQuery({
    queryKey: ["job-trajectory-index", jobId],
    queryFn: () => fetchTrajectoryIndex(jobId!),
    enabled: !!jobId,
  });

  const { data: idea } = useQuery({
    queryKey: ["job-idea", jobId],
    queryFn: () => fetchIdea(jobId!),
    enabled: !!jobId,
  });

  if (!jobId) return null;

  return (
    <div className="container mx-auto py-6 px-4 max-w-7xl">
      {/* Breadcrumb */}
      <Breadcrumb className="mb-4">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link to="/">Jobs</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage className="font-mono text-xs max-w-[400px] truncate">
              {jobId}
            </BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      {/* Header */}
      {metaLoading ? (
        <div className="mb-6">
          <LoadingDots />
        </div>
      ) : meta ? (
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Link
              to="/"
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="h-5 w-5" />
            </Link>
            <div>
              <h1 className="text-xl font-bold tracking-tight font-mono truncate max-w-[500px]">
                {jobId}
              </h1>
              <div className="flex items-center gap-2 mt-1">
                <StatusBadge status={meta.status} />
                <Badge variant="secondary" className="text-xs font-normal">
                  {meta.model}
                </Badge>
                {meta.duration_seconds != null && (
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {formatDuration(meta.duration_seconds)}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4 text-sm">
            {trajectoryIndex && (
              <span className="text-muted-foreground flex items-center gap-1">
                <Route className="h-3.5 w-3.5" />
                {trajectoryIndex.total_steps} steps
              </span>
            )}
            {tokens?.cost && (
              <span className="text-amber-500 font-medium flex items-center gap-1">
                <DollarSign className="h-3.5 w-3.5" />
                ${tokens.cost.estimated_cost_usd.toFixed(2)}
              </span>
            )}
            {meta.submissions > 0 && (
              <span className="text-muted-foreground flex items-center gap-1">
                <FileText className="h-3.5 w-3.5" />
                v{meta.submissions}
              </span>
            )}
            {meta.gitlab_url && (
              <a
                href={meta.gitlab_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-muted-foreground hover:text-foreground flex items-center gap-1"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                GitLab
              </a>
            )}
          </div>
        </div>
      ) : null}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="submissions" className="flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5" />
            Submissions
            {submissionsData && submissionsData.total > 0 && (
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0 ml-1">
                {submissionsData.total}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="trajectory" className="flex items-center gap-1.5">
            <Route className="h-3.5 w-3.5" />
            Trajectory
            {trajectoryIndex && (
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0 ml-1">
                {trajectoryIndex.total_steps}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="submissions" className="mt-4">
          <SubmissionsTab
            jobId={jobId}
            submissions={submissionsData?.submissions ?? []}
          />
        </TabsContent>

        <TabsContent value="trajectory" className="mt-4">
          <TrajectoryTab
            jobId={jobId}
            index={trajectoryIndex ?? null}
            tokens={tokens ?? null}
            idea={idea ?? null}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
