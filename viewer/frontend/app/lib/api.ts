import type {
  Artifacts,
  IdeaPayload,
  JobMeta,
  JobSummary,
  StepDetail,
  SubmissionsResponse,
  TokenMetrics,
  TrajectoryIndex,
} from "./types";

// In production (served from same origin): use relative URL
// In dev: Vite proxy forwards /api to the backend
const API_BASE = import.meta.env.VITE_API_URL ?? "";

// ---- Jobs list ----

export async function fetchJobs(): Promise<JobSummary[]> {
  const response = await fetch(`${API_BASE}/api/jobs`);
  if (!response.ok) {
    throw new Error(`Failed to fetch jobs: ${response.statusText}`);
  }
  return response.json();
}

// ---- Job detail ----

export async function fetchJobMeta(jobId: string): Promise<JobMeta> {
  const response = await fetch(
    `${API_BASE}/api/jobs/${encodeURIComponent(jobId)}/meta`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch job meta: ${response.statusText}`);
  }
  return response.json();
}

// ---- Trajectory index (lightweight) ----

export async function fetchTrajectoryIndex(
  jobId: string
): Promise<TrajectoryIndex | null> {
  const response = await fetch(
    `${API_BASE}/api/jobs/${encodeURIComponent(jobId)}/trajectory/index`
  );
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`Failed to fetch trajectory index: ${response.statusText}`);
  }
  return response.json();
}

// ---- Single step detail (loaded on demand) ----

export async function fetchStepDetail(
  jobId: string,
  stepId: number
): Promise<StepDetail> {
  const response = await fetch(
    `${API_BASE}/api/jobs/${encodeURIComponent(jobId)}/trajectory/step/${stepId}`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch step ${stepId}: ${response.statusText}`);
  }
  return response.json();
}

// ---- Token metrics ----

export async function fetchTokenMetrics(
  jobId: string
): Promise<TokenMetrics> {
  const response = await fetch(
    `${API_BASE}/api/jobs/${encodeURIComponent(jobId)}/tokens`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch tokens: ${response.statusText}`);
  }
  return response.json();
}

// ---- Idea ----

export async function fetchIdea(jobId: string): Promise<IdeaPayload> {
  const response = await fetch(
    `${API_BASE}/api/jobs/${encodeURIComponent(jobId)}/idea`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch idea: ${response.statusText}`);
  }
  return response.json();
}

// ---- Submissions ----

export async function fetchSubmissions(
  jobId: string
): Promise<SubmissionsResponse> {
  const response = await fetch(
    `${API_BASE}/api/jobs/${encodeURIComponent(jobId)}/submissions`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch submissions: ${response.statusText}`);
  }
  return response.json();
}

export function getSubmissionPdfUrl(jobId: string, directory: string): string {
  return `${API_BASE}/api/jobs/${encodeURIComponent(jobId)}/submissions/${encodeURIComponent(directory)}/paper`;
}

// ---- Artifacts ----

export async function fetchArtifacts(jobId: string): Promise<Artifacts> {
  const response = await fetch(
    `${API_BASE}/api/jobs/${encodeURIComponent(jobId)}/artifacts`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch artifacts: ${response.statusText}`);
  }
  return response.json();
}
