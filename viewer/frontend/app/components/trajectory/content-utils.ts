import type { ContentPart } from "~/lib/types";

export function isContentPart(value: unknown): value is ContentPart {
  if (!value || typeof value !== "object") return false;
  const part = value as Record<string, unknown>;
  return part.type === "text" || part.type === "image";
}

export function parseStructuredContent(content: unknown): ContentPart[] | null {
  if (Array.isArray(content)) {
    const parts = content.filter(isContentPart);
    return parts.length > 0 ? parts : null;
  }

  if (isContentPart(content)) {
    return [content];
  }

  if (typeof content !== "string") {
    return null;
  }

  const trimmed = content.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) {
    return null;
  }

  try {
    return parseStructuredContent(JSON.parse(trimmed));
  } catch {
    return null;
  }
}

export function getImageSrc(part: ContentPart, jobId: string): string | null {
  if (!part.source) return null;

  if (part.source.path) {
    return `/api/jobs/${encodeURIComponent(jobId)}/artifacts/${part.source.path}`;
  }

  if (part.source.type === "base64" && part.source.data) {
    const mediaType = part.source.media_type || "image/png";
    return `data:${mediaType};base64,${part.source.data}`;
  }

  return null;
}

export function getImageLabel(part: ContentPart): string {
  if (part.source?.path) {
    return part.source.path;
  }

  if (part.source?.type === "base64") {
    return part.source.media_type || "inline image";
  }

  return "image";
}
