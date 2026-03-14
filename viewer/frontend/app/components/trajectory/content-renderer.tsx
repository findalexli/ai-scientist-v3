import { useState } from "react";
import { ImageOff } from "lucide-react";
import type { ContentPart, MessageContent, ObservationContent } from "~/lib/types";
import {
  getImageLabel,
  getImageSrc,
  parseStructuredContent,
} from "./content-utils";

interface ContentRendererProps {
  content: MessageContent | ObservationContent;
  jobId: string;
  className?: string;
}

interface ImageError {
  status: number;
  message: string;
}

function ImageWithFallback({
  src,
  label,
}: {
  src: string;
  label: string;
}) {
  const [error, setError] = useState<ImageError | null>(null);

  const handleError = async () => {
    if (src.startsWith("data:")) {
      setError({ status: 0, message: "Failed to decode embedded image" });
      return;
    }

    try {
      const response = await fetch(src);
      let message = response.statusText || "Failed to load image";
      if (!response.ok) {
        try {
          const json = await response.json();
          message = json.detail || message;
        } catch {
          // not JSON
        }
      }
      setError({ status: response.status, message });
    } catch {
      setError({ status: 0, message: "Network error" });
    }
  };

  if (error) {
    return (
      <div className="my-2">
        <div className="text-sm bg-muted/50 rounded border border-dashed border-muted-foreground/50 p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-2">
            <ImageOff className="h-4 w-4" />
            <span className="font-medium">Image unavailable</span>
            {error.status > 0 && (
              <span className="text-xs bg-muted px-1.5 py-0.5 rounded">
                {error.status}
              </span>
            )}
          </div>
          <div className="text-xs font-mono text-muted-foreground/80 break-all">{label}</div>
          <div className="text-xs text-muted-foreground/60 mt-2">
            {error.message}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="my-2">
      <img
        src={src}
        alt={`Image: ${label}`}
        className="max-w-full h-auto rounded border border-border"
        style={{ maxHeight: "400px" }}
        loading="lazy"
        onError={handleError}
      />
      <div className="text-xs text-muted-foreground mt-1">{label}</div>
    </div>
  );
}

export function getTextFromContent(content: MessageContent | ObservationContent): string {
  if (content === null || content === undefined) return "";
  if (typeof content === "string") return content;
  return content
    .filter((part): part is ContentPart & { type: "text" } => part.type === "text")
    .map((part) => part.text || "")
    .join("\n");
}

export function getFirstLine(content: MessageContent | ObservationContent): string | null {
  const text = getTextFromContent(content);
  return text?.split("\n")[0] || null;
}

export function ContentRenderer({
  content,
  jobId,
  className = "",
}: ContentRendererProps) {
  if (content === null || content === undefined) {
    return <span className="text-muted-foreground italic">(empty)</span>;
  }

  if (typeof content === "string") {
    const parsedContent = parseStructuredContent(content);
    if (parsedContent) {
      return <ContentRenderer content={parsedContent} jobId={jobId} className={className} />;
    }

    return (
      <div className={`text-sm whitespace-pre-wrap break-words ${className}`}>
        {content || <span className="text-muted-foreground italic">(empty)</span>}
      </div>
    );
  }

  return (
    <div className={`space-y-3 ${className}`}>
      {content.map((part, idx) => {
        if (part.type === "text") {
          return (
            <div key={idx} className="text-sm whitespace-pre-wrap break-words">
              {part.text}
            </div>
          );
        }

        if (part.type === "image" && part.source) {
          const imageUrl = getImageSrc(part, jobId);
          if (!imageUrl) {
            return null;
          }

          return (
            <ImageWithFallback
              key={idx}
              src={imageUrl}
              label={getImageLabel(part)}
            />
          );
        }

        return null;
      })}
    </div>
  );
}

export function ObservationContentRenderer({
  content,
  jobId,
}: {
  content: ObservationContent;
  jobId: string;
}) {
  if (content === null || content === undefined) {
    return <span className="text-muted-foreground italic">(empty)</span>;
  }

  return <ContentRenderer content={content} jobId={jobId} />;
}
