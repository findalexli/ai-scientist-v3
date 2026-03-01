import { FileText, ExternalLink } from "lucide-react";
import { useState } from "react";

import { Badge } from "~/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "~/components/ui/empty";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { ScrollArea } from "~/components/ui/scroll-area";
import { getSubmissionPdfUrl } from "~/lib/api";
import type { Submission } from "~/lib/types";
import { MarkdownRenderer } from "./markdown-renderer";
import { PdfViewer } from "./pdf-viewer";

/** Parse timestamps like "20260226_072058" into displayable strings */
function formatTimestamp(ts: string | null): string {
  if (!ts) return "Unknown date";
  // Try ISO format first
  const isoDate = new Date(ts);
  if (!isNaN(isoDate.getTime())) return isoDate.toLocaleString();
  // Try YYYYMMDD_HHMMSS format
  const m = ts.match(/^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$/);
  if (m) {
    const [, y, mo, d, h, mi, s] = m;
    return new Date(+y, +mo - 1, +d, +h, +mi, +s).toLocaleString();
  }
  return ts;
}

interface Props {
  jobId: string;
  submissions: Submission[];
}

export function SubmissionsTab({ jobId, submissions }: Props) {
  const [selectedIdx, setSelectedIdx] = useState(0);
  const safeIdx = Math.min(selectedIdx, Math.max(0, submissions.length - 1));

  if (submissions.length === 0) {
    return (
      <Empty className="bg-card border">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <FileText />
          </EmptyMedia>
          <EmptyTitle>No submissions yet</EmptyTitle>
          <EmptyDescription>
            This job has not been submitted for review.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  const sub = submissions[safeIdx];
  const pdfUrl = sub?.paper_url ?? getSubmissionPdfUrl(jobId, sub?.directory ?? "");

  return (
    <div className="grid grid-cols-[280px_1fr] gap-4">
      {/* Version sidebar */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Versions</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <ScrollArea className="max-h-[70vh]">
            <div className="flex flex-col">
              {submissions.map((s, i) => (
                <button
                  key={s.directory}
                  onClick={() => setSelectedIdx(i)}
                  className={`text-left px-4 py-3 border-b last:border-b-0 transition-colors ${
                    i === selectedIdx
                      ? "bg-accent text-accent-foreground"
                      : "hover:bg-muted/50"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-xs font-mono">
                      v{s.version}
                    </Badge>
                    {s.reviewer_mode && (
                      <Badge variant="secondary" className="text-[10px]">
                        {s.reviewer_mode}
                      </Badge>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {formatTimestamp(s.timestamp)}
                  </div>
                </button>
              ))}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>

      {/* Main content */}
      <div className="space-y-4">
        {/* PDF */}
        {sub?.paper_url && (
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">Paper</CardTitle>
                <a
                  href={pdfUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                >
                  Open in new tab
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            </CardHeader>
            <CardContent>
              <PdfViewer url={pdfUrl} />
            </CardContent>
          </Card>
        )}

        {/* Review */}
        {sub?.review_markdown && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Review</CardTitle>
            </CardHeader>
            <CardContent>
              <MarkdownRenderer content={sub.review_markdown} />
            </CardContent>
          </Card>
        )}

        {/* Rebuttal */}
        {sub?.rebuttal_markdown && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Rebuttal</CardTitle>
            </CardHeader>
            <CardContent>
              <MarkdownRenderer content={sub.rebuttal_markdown} />
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
