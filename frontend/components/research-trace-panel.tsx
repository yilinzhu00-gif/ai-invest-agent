"use client";

import type { AgentEvent } from "../lib/sse/agent-events";

type TraceStep = { key: string; label: string; start: string[]; end: string[] };

const STEPS: TraceStep[] = [
  { key: "planning", label: "Task Planning", start: ["PLANNING_START"], end: [] },
  { key: "financial", label: "Financial Analysis", start: ["Financial Agent started", "agent.analyst.started"], end: ["agent.analyst.completed"] },
  { key: "news", label: "News Agent", start: ["Evidence search started", "TOOL_CALL_START"], end: ["Evidence search completed", "TOOL_CALL_END"] },
  { key: "reflection", label: "Reflection", start: ["REFLECTION_START", "agent.numeric_validator.started", "agent.reviewer.started"], end: ["agent.reviewer.completed", "agent.numeric_validator.completed"] },
  { key: "report", label: "Report Generation", start: ["REPORT_GENERATE_START"], end: ["research.result", "research.evidence_result", "run.completed"] },
];

function eventType(event: AgentEvent): string {
  return typeof event.data.type === "string" ? event.data.type : event.event;
}

function matches(event: AgentEvent, values: string[]): boolean {
  const type = eventType(event);
  const message = typeof event.data.message === "string" ? event.data.message : "";
  return values.includes(type) || values.includes(event.event) || values.some((value) => message.includes(value));
}

export function ResearchTracePanel({ events, active }: { events: AgentEvent[]; active: boolean }) {
  return (
    <section className="research-trace-panel" aria-label="Research Trace Panel">
      <div className="research-trace-heading">
        <div><p className="section-label">AGENT TRACE</p><h3>Research execution</h3></div>
        {active && <span className="research-trace-live"><span className="status-dot" /> Live</span>}
      </div>
      <ol className="research-trace-list">
        {STEPS.map((step, index) => {
          const started = events.some((event) => matches(event, step.start));
          const finished = (step.end.length > 0 && events.some((event) => matches(event, step.end))) || (!active && started);
          const state = finished ? "done" : started ? "running" : "pending";
          return (
            <li key={step.key} className={`research-trace-step research-trace-step--${state}`}>
              <span className="research-trace-marker" aria-hidden="true">{state === "done" ? "✓" : state === "running" ? "⏳" : "○"}</span>
              <span><strong>{step.label}</strong><small>{state === "done" ? "Completed" : state === "running" ? "Running" : index === 0 && active ? "Queued" : "Waiting"}</small></span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
