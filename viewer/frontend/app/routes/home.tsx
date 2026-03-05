import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { FlaskConical, Search } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { Badge } from "~/components/ui/badge";
import {
  DataTable,
  SortableHeader,
} from "~/components/ui/data-table";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "~/components/ui/empty";
import { Input } from "~/components/ui/input";
import { LoadingDots } from "~/components/ui/loading-dots";
import { fetchJobs } from "~/lib/api";
import { useDebouncedValue, useKeyboardTableNavigation } from "~/lib/hooks";
import type { JobSummary } from "~/lib/types";

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "-";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    running: "bg-green-500 animate-pulse",
    completed: "bg-blue-500",
    idle: "bg-yellow-500",
    unknown: "bg-gray-500",
  };
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${colors[status] ?? colors.unknown}`}
    />
  );
}

const columns: ColumnDef<JobSummary>[] = [
  {
    accessorKey: "status",
    header: "",
    size: 40,
    cell: ({ row }) => <StatusDot status={row.original.status} />,
    enableSorting: false,
  },
  {
    accessorKey: "id",
    header: ({ column }) => (
      <SortableHeader column={column}>Job ID</SortableHeader>
    ),
    cell: ({ row }) => (
      <span className="font-mono text-xs truncate max-w-[480px] block" title={row.original.id}>
        {row.original.id}
      </span>
    ),
  },
  {
    accessorKey: "model",
    header: ({ column }) => (
      <SortableHeader column={column}>Model</SortableHeader>
    ),
    cell: ({ row }) => (
      <Badge variant="secondary" className="text-xs font-normal">
        {row.original.model}
      </Badge>
    ),
  },
  {
    accessorKey: "duration_seconds",
    header: ({ column }) => (
      <SortableHeader column={column}>Duration</SortableHeader>
    ),
    cell: ({ row }) => (
      <span className="text-xs text-muted-foreground">
        {formatDuration(row.original.duration_seconds)}
      </span>
    ),
  },
  {
    id: "tokens",
    header: ({ column }) => (
      <SortableHeader column={column}>Tokens</SortableHeader>
    ),
    accessorFn: (row) => {
      if (!row.tokens) return 0;
      return row.tokens.input_tokens + row.tokens.output_tokens;
    },
    cell: ({ row }) => {
      const t = row.original.tokens;
      if (!t) return <span className="text-xs text-muted-foreground">-</span>;
      return (
        <span className="text-xs text-muted-foreground">
          {formatTokens(t.input_tokens + t.output_tokens)}
        </span>
      );
    },
  },
  {
    id: "cost",
    header: ({ column }) => (
      <SortableHeader column={column}>Cost</SortableHeader>
    ),
    accessorFn: (row) => row.tokens?.estimated_cost_usd ?? 0,
    cell: ({ row }) => {
      const cost = row.original.tokens?.estimated_cost_usd;
      if (cost == null) return <span className="text-xs text-muted-foreground">-</span>;
      return (
        <span className="text-xs font-medium text-amber-500">
          ${cost.toFixed(2)}
        </span>
      );
    },
  },
  {
    accessorKey: "submissions",
    header: ({ column }) => (
      <SortableHeader column={column}>Subs</SortableHeader>
    ),
    cell: ({ row }) => {
      const n = row.original.submissions;
      if (n === 0) return <span className="text-xs text-muted-foreground">-</span>;
      return (
        <Badge variant="outline" className="text-xs font-normal">
          v{n}
        </Badge>
      );
    },
  },
];

export default function HomePage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search, 200);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const { data: jobs, isLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: fetchJobs,
    refetchInterval: 10_000,
  });

  const filteredJobs = useMemo(() => {
    if (!jobs) return [];
    let result = jobs;
    if (debouncedSearch) {
      const q = debouncedSearch.toLowerCase();
      result = result.filter(
        (j) =>
          j.id.toLowerCase().includes(q) ||
          j.model.toLowerCase().includes(q) ||
          (j.task_name && j.task_name.toLowerCase().includes(q))
      );
    }
    if (statusFilter) {
      result = result.filter((j) => j.status === statusFilter);
    }
    return result;
  }, [jobs, debouncedSearch, statusFilter]);

  const statusCounts = useMemo(() => {
    if (!jobs) return {};
    const counts: Record<string, number> = {};
    for (const j of jobs) {
      counts[j.status] = (counts[j.status] ?? 0) + 1;
    }
    return counts;
  }, [jobs]);

  const totalCost = useMemo(() => {
    if (!jobs) return 0;
    return jobs.reduce((sum, j) => sum + (j.tokens?.estimated_cost_usd ?? 0), 0);
  }, [jobs]);

  const { highlightedIndex } = useKeyboardTableNavigation({
    rows: filteredJobs,
    onNavigate: (job) => navigate(`/jobs/${encodeURIComponent(job.id)}`),
  });

  return (
    <div className="container mx-auto py-6 px-4 max-w-7xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">AI Scientist</h1>
          <p className="text-sm text-muted-foreground">Job Monitor</p>
        </div>
        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <span>{jobs?.length ?? 0} jobs</span>
          <span>{statusCounts.running ?? 0} running</span>
          <span className="text-amber-500 font-medium">${totalCost.toFixed(2)}</span>
        </div>
      </div>

      {/* Search + Filters */}
      <div className="flex items-center gap-3 mb-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            ref={searchRef}
            placeholder="Search jobs..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex gap-1.5">
          <Badge
            variant={statusFilter === null ? "default" : "outline"}
            className="cursor-pointer text-xs"
            onClick={() => setStatusFilter(null)}
          >
            All ({jobs?.length ?? 0})
          </Badge>
          {Object.entries(statusCounts).map(([status, count]) => (
            <Badge
              key={status}
              variant={statusFilter === status ? "default" : "outline"}
              className="cursor-pointer text-xs"
              onClick={() =>
                setStatusFilter(statusFilter === status ? null : status)
              }
            >
              {status} ({count})
            </Badge>
          ))}
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <LoadingDots />
        </div>
      ) : filteredJobs.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <FlaskConical />
            </EmptyMedia>
            <EmptyTitle>No jobs found</EmptyTitle>
            <EmptyDescription>
              {search
                ? "Try adjusting your search query."
                : "No jobs available yet."}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <DataTable
          columns={columns}
          data={filteredJobs}
          onRowClick={(job) =>
            navigate(`/jobs/${encodeURIComponent(job.id)}`)
          }
          highlightedIndex={highlightedIndex}
        />
      )}
    </div>
  );
}
