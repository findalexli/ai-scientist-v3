import { ChevronDown, ChevronRight, FileJson } from "lucide-react";
import { useState, useMemo } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { CodeBlock } from "~/components/ui/code-block";
import type { IdeaPayload } from "~/lib/types";

interface Props {
  idea: IdeaPayload;
}

export function IdeaCard({ idea }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  const parsed = useMemo(() => {
    if (idea.format === "json" && idea.content) {
      try {
        return JSON.parse(idea.content);
      } catch {
        return null;
      }
    }
    return null;
  }, [idea.content, idea.format]);

  if (!idea.found || !idea.content) return null;

  const title = parsed?.Name || parsed?.Title || idea.stem || "Idea Input";

  return (
    <Card>
      <CardHeader
        className="pb-3 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {expanded ? (
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            )}
            <FileJson className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-sm">{title}</CardTitle>
          </div>
          {idea.source && (
            <span className="text-xs text-muted-foreground">{idea.source}</span>
          )}
        </div>
      </CardHeader>
      {expanded && (
        <CardContent>
          <div className="flex justify-end mb-2">
            <button
              className="text-xs text-muted-foreground hover:text-foreground"
              onClick={(e) => {
                e.stopPropagation();
                setShowRaw(!showRaw);
              }}
            >
              {showRaw ? "Show formatted" : "Show raw JSON"}
            </button>
          </div>
          {showRaw || !parsed ? (
            <CodeBlock
              code={
                typeof idea.content === "string"
                  ? idea.content
                  : JSON.stringify(idea.content, null, 2)
              }
              lang="json"
            />
          ) : (
            <IdeaFields data={parsed} />
          )}
        </CardContent>
      )}
    </Card>
  );
}

function IdeaFields({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="space-y-3">
      {Object.entries(data).map(([key, value]) => (
        <div key={key} className="border-l-2 border-border pl-3">
          <div className="text-xs font-medium text-muted-foreground uppercase mb-0.5">
            {key}
          </div>
          <IdeaValue value={value} />
        </div>
      ))}
    </div>
  );
}

function IdeaValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="text-xs text-muted-foreground italic">null</span>;
  }

  if (typeof value === "string") {
    return <div className="text-sm whitespace-pre-wrap">{value}</div>;
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return <span className="text-sm font-mono">{String(value)}</span>;
  }

  if (Array.isArray(value)) {
    return (
      <div className="space-y-1 pl-2">
        {value.map((item, i) => (
          <div key={i} className="flex gap-2 text-sm">
            <span className="text-muted-foreground shrink-0">{i + 1}.</span>
            <IdeaValue value={item} />
          </div>
        ))}
      </div>
    );
  }

  if (typeof value === "object") {
    return <IdeaFields data={value as Record<string, unknown>} />;
  }

  return <span className="text-sm">{String(value)}</span>;
}
