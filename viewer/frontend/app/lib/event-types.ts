export interface EventTypeConfig {
  label: string;
  color: string;
}

export const EVENT_TYPES: Record<string, EventTypeConfig> = {
  literature: { label: "Literature", color: "#a07cff" },
  experiment: { label: "Experiment", color: "#3dd9a4" },
  paper: { label: "Paper", color: "#5cb8ff" },
  submission: { label: "Submission", color: "#ff6a96" },
  plotting: { label: "Plotting", color: "#60e6ff" },
  system: { label: "System", color: "#5a7490" },
  web: { label: "Web", color: "#ffaa44" },
  thinking: { label: "Thinking", color: "#8899aa" },
};

export function getEventTypeConfig(eventType: string): EventTypeConfig {
  return EVENT_TYPES[eventType] ?? { label: eventType, color: "#5a7490" };
}
