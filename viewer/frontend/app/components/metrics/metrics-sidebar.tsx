import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import type { TokenMetrics } from "~/lib/types";
import { getEventTypeConfig } from "~/lib/event-types";

interface Props {
  tokens: TokenMetrics | null;
}

function formatTokens(n: number | undefined): string {
  if (n == null) return "-";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function MetricsSidebar({ tokens }: Props) {
  if (!tokens) return null;

  return (
    <div className="space-y-4 sticky top-4">
      {/* Cost summary */}
      {tokens.cost && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Cost Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Estimated Cost</span>
              <span className="font-medium text-amber-500">
                ${tokens.cost.estimated_cost_usd.toFixed(2)}
              </span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Input Tokens</span>
              <span>{formatTokens(tokens.cost.input_tokens)}</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Output Tokens</span>
              <span>{formatTokens(tokens.cost.output_tokens)}</span>
            </div>
            {(tokens.cost.cache_read_tokens ?? 0) > 0 && (
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">Cache Read</span>
                <span>{formatTokens(tokens.cost.cache_read_tokens)}</span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Tool breakdown */}
      {tokens.tool_breakdown.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Tool Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5">
              {tokens.tool_breakdown.slice(0, 15).map((item, i) => (
                <div key={item.tool ?? i} className="flex items-center gap-2 text-xs">
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between">
                      <span className="font-mono truncate">{item.tool ?? "unknown"}</span>
                      <span className="text-muted-foreground shrink-0 ml-2">
                        {item.count}
                      </span>
                    </div>
                    <div className="h-1 bg-muted rounded-full mt-0.5">
                      <div
                        className="h-full bg-primary/40 rounded-full"
                        style={{ width: `${item.pct}%` }}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Activity breakdown */}
      {tokens.event_type_breakdown.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Activity Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5">
              {tokens.event_type_breakdown.map((item) => {
                const cfg = getEventTypeConfig(item.type ?? "");
                return (
                  <div
                    key={item.type}
                    className="flex items-center gap-2 text-xs"
                  >
                    <span
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ backgroundColor: cfg.color }}
                    />
                    <span className="flex-1">{cfg.label}</span>
                    <span className="text-muted-foreground">
                      {item.count} ({item.pct}%)
                    </span>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
