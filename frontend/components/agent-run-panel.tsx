"use client";

import { useEffect, useState } from "react";

import { readAgentEvents, type AgentEvent } from "../lib/sse/agent-events";

type AgentRun = { id: string; status: string; executor_mode: string };

const storageKey = "investment-agent:last-run";
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const developmentHeaders = {
  "X-Development-Principal-ID": "demo-analyst",
  "X-Development-Workspace-ID": "demo-workspace",
};

async function readRun(runId: string): Promise<AgentRun> {
  const response = await fetch(`${apiBaseUrl}/api/v1/agent/runs/${runId}`, { headers: developmentHeaders });
  if (!response.ok) throw new Error("run_not_found");
  return response.json() as Promise<AgentRun>;
}

export function AgentRunPanel() {
  const [run, setRun] = useState<AgentRun | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");

  useEffect(() => {
    const savedRunId = window.localStorage.getItem(storageKey);
    if (!savedRunId) return;
    const runId: string = savedRunId;
    let cancelled = false;
    async function restore() {
      try {
        const persistedRun = await readRun(runId);
        if (cancelled) return;
        setRun(persistedRun);
        const response = await fetch(`${apiBaseUrl}/api/v1/agent/runs/${runId}/events`, {
          headers: { ...developmentHeaders, "Last-Event-ID": "0" },
        });
        if (!response.ok) throw new Error("events_unavailable");
        for await (const event of readAgentEvents(response)) {
          if (cancelled) return;
          if (event.id !== null || event.event !== "heartbeat") setEvents((existing) => [...existing, event]);
        }
      } catch {
        if (!cancelled) setError("无法恢复该研究任务，请创建新的任务后重试。");
      }
    }
    void restore();
    return () => { cancelled = true; };
  }, []);

  async function createRun() {
    if (!question.trim()) return;
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/runs`, {
        method: "POST",
        headers: { ...developmentHeaders, "content-type": "application/json" },
        body: JSON.stringify({ question: question.trim() }),
      });
      if (!response.ok) throw new Error("run_create_failed");
      const created = await response.json() as AgentRun;
      window.localStorage.setItem(storageKey, created.id);
      setEvents([]);
      setError(null);
      setRun(created);
    } catch {
      setError("无法创建研究任务，请稍后重试。");
    }
  }

  async function cancelRun() {
    if (!run) return;
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/runs/${run.id}/cancel`, {
        method: "POST",
        headers: developmentHeaders,
      });
      if (!response.ok) throw new Error("run_cancel_failed");
      setRun(await response.json() as AgentRun);
    } catch {
      setError("无法取消研究任务，请稍后重试。");
    }
  }

  return (
    <section className="agent-run-panel" aria-label="研究任务">
      <h2>研究任务</h2>
      <p>开发环境仅展示可恢复的 Run 与 SSE 事件；生产队列将在阶段三替换当前执行器。</p>
      <label>
        研究问题
        <input value={question} onChange={(event) => setQuestion(event.target.value)} />
      </label>
      <button type="button" onClick={() => void createRun()} disabled={!question.trim()}>启动研究</button>
      {run && <p>状态：{run.status}</p>}
      {run && !["completed", "failed", "cancelled"].includes(run.status) && (
        <button type="button" onClick={() => void cancelRun()}>取消任务</button>
      )}
      {error && <p className="error-card" role="alert">{error}</p>}
      {events.map((event, index) => (
        <p key={`${event.id ?? "heartbeat"}-${index}`} className="agent-event">
          {typeof event.data.text === "string" ? event.data.text : event.event}
        </p>
      ))}
    </section>
  );
}
