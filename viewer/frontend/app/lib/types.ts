// ---- Dashboard job list ----

export interface JobSummary {
  id: string;
  status: "running" | "completed" | "idle" | "unknown";
  duration_seconds: number | null;
  model: string;
  line_count: number;
  file_size_mb: number;
  submissions: number;
  tokens: TokenSummary | null;
  task_name: string;
}

export interface TokenSummary {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  model?: string;
}

// ---- Job metadata ----

export interface JobMeta {
  id: string;
  status: "running" | "completed" | "idle" | "unknown";
  duration_seconds: number | null;
  model: string;
  submissions: number;
  gitlab_url?: string;
}

// ---- Submissions ----

export interface Submission {
  version: number;
  timestamp: string;
  directory: string;
  reviewer_mode: string | null;
  review_markdown: string;
  rebuttal_markdown: string | null;
  paper_url: string | null;
}

export interface SubmissionsResponse {
  submissions: Submission[];
  total: number;
}

// ---- Idea ----

export interface IdeaPayload {
  found: boolean;
  stem: string | null;
  source: string | null;
  content: string | null;
  format: "json" | "text" | null;
}

// ---- Token metrics ----

export interface CostMetrics {
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  estimated_cost_usd: number;
  model?: string;
}

export interface CumulativeToken {
  step: number;
  input_tokens: number;
  output_tokens: number;
  cache_read: number;
  cache_creation: number;
  total: number;
}

export interface BreakdownItem {
  tool?: string;
  type?: string;
  count: number;
  pct: number;
}

export interface TokenMetrics {
  cost: CostMetrics | null;
  cumulative_tokens: CumulativeToken[];
  tool_breakdown: BreakdownItem[];
  event_type_breakdown: BreakdownItem[];
}

// ---- Trajectory index (lightweight, for virtual scrolling) ----

export interface StepSummary {
  step_id: number;
  source: "system" | "user" | "agent";
  timestamp: string | null;
  event_type: string;
  summary: string;
  tool_names: string[];
  has_reasoning: boolean;
  prompt_tokens: number;
  completion_tokens: number;
  cache_read: number;
  cache_creation: number;
  byte_offset: number;
  byte_length: number;
}

export interface TrajectoryIndex {
  total_steps: number;
  agent: {
    name: string;
    model_name: string | null;
  } | null;
  session_id: string | null;
  final_metrics: {
    total_prompt_tokens: number | null;
    total_completion_tokens: number | null;
    total_cached_tokens: number | null;
    total_steps: number | null;
  } | null;
  steps: StepSummary[];
}

// ---- Full ATIF step (loaded on demand) ----

export interface ContentPart {
  type: "text" | "image";
  text?: string;
  source?: { media_type: string; path: string };
}

export type MessageContent = string | ContentPart[];
export type ObservationContent = string | ContentPart[] | null;

export interface ToolCall {
  tool_call_id: string;
  function_name: string;
  arguments: Record<string, unknown>;
}

export interface ObservationResult {
  source_call_id: string | null;
  content: ObservationContent;
}

export interface StepDetail {
  step_id: number;
  timestamp: string | null;
  source: "system" | "user" | "agent";
  model_name: string | null;
  message: MessageContent;
  reasoning_content: string | null;
  tool_calls: ToolCall[] | null;
  observation: { results: ObservationResult[] } | null;
  metrics: {
    prompt_tokens: number | null;
    completion_tokens: number | null;
    cached_tokens: number | null;
  } | null;
}

// ---- Artifacts ----

export interface Artifacts {
  figures: string[];
  papers: string[];
}

// ---- SSE events ----

export interface SSEMetrics {
  cost: CostMetrics | null;
  cumulative_tokens: CumulativeToken[];
  tool_breakdown: BreakdownItem[];
  event_type_breakdown: BreakdownItem[];
  total_lines: number;
}
