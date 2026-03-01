import { CodeBlock } from "~/components/ui/code-block";
import {
  ContentRenderer,
  ObservationContentRenderer,
} from "./content-renderer";
import type { StepDetail } from "~/lib/types";

interface Props {
  step: StepDetail;
  jobId: string;
}

export function StepContent({ step, jobId }: Props) {
  return (
    <div className="space-y-3">
      {/* Message */}
      {step.message && (
        <ContentRenderer
          content={step.message}
          jobId={jobId}
        />
      )}

      {/* Reasoning (filter out literal "null" string from ATIF) */}
      {step.reasoning_content && step.reasoning_content !== "null" && (
        <div>
          <h5 className="text-xs font-medium text-muted-foreground mb-1">
            Reasoning
          </h5>
          <pre className="text-xs bg-muted p-2 overflow-x-auto whitespace-pre-wrap rounded">
            {step.reasoning_content}
          </pre>
        </div>
      )}

      {/* Tool calls */}
      {step.tool_calls && step.tool_calls.length > 0 && (
        <div>
          <h5 className="text-xs font-medium text-muted-foreground mb-1">
            Tool Calls
          </h5>
          {step.tool_calls.map((tc) => (
            <div key={tc.tool_call_id} className="mb-2">
              <div className="text-xs font-mono mb-1 text-purple-600 dark:text-purple-300">
                {tc.function_name}
              </div>
              <CodeBlock
                code={JSON.stringify(tc.arguments, null, 2)}
                lang="json"
              />
            </div>
          ))}
        </div>
      )}

      {/* Observations */}
      {step.observation && step.observation.results.length > 0 && (
        <div>
          <h5 className="text-xs font-medium text-muted-foreground mb-1">
            Observations
          </h5>
          {step.observation.results.map((result, idx) => (
            <div key={idx} className="mb-2">
              <ObservationContentRenderer
                content={result.content}
                jobId={jobId}
              />
            </div>
          ))}
        </div>
      )}

      {/* Metrics */}
      {step.metrics && (
        <div className="text-xs text-muted-foreground">
          Tokens: {(step.metrics.prompt_tokens ?? 0).toLocaleString()} prompt /{" "}
          {(step.metrics.completion_tokens ?? 0).toLocaleString()} completion
        </div>
      )}
    </div>
  );
}
