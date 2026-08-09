"use client";

import { useEffect, useState } from "react";

import { useAuth } from "./auth-provider";
import { readAgentEvents, type AgentEvent } from "../lib/sse/agent-events";

type AgentRun = { id: string; status: string; executor_mode: string };

const storageKey = "investment-agent:last-run";
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const terminalStatuses = new Set(["completed", "failed", "cancelled"]);
const reconnectDelayMs = 1_000;
async function readRun(runId: string, headers: HeadersInit): Promise<AgentRun> {
  const response = await fetch(`${apiBaseUrl}/api/v1/agent/runs/${runId}`, { headers });
  if (!response.ok) throw new Error("run_not_found");
  return response.json() as Promise<AgentRun>;
}

export function AgentRunPanel() {
  const auth = useAuth();
  const [run, setRun] = useState<AgentRun | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");

  async function subscribeToEvents(runId: string, headers: HeadersInit, initialStatus: string, isCancelled = () => false) {
    let lastEventId = 0;
    let currentStatus = initialStatus;
    while (!isCancelled()) {
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/runs/${runId}/events`, {
        headers: { ...headers, "Last-Event-ID": String(lastEventId) },
      });
      if (!response.ok) throw new Error("events_unavailable");
      for await (const event of readAgentEvents(response)) {
        if (isCancelled()) return;
        if (event.id !== null) {
          if (event.id <= lastEventId) continue;
          lastEventId = event.id;
        }
        if (event.event !== "heartbeat") {
          setEvents((existing) => event.id !== null && existing.some((saved) => saved.id === event.id)
            ? existing
            : [...existing, event]);
        }
      }
      if (isCancelled() || terminalStatuses.has(currentStatus)) return;
      const persistedRun = await readRun(runId, headers);
      if (isCancelled()) return;
      setRun(persistedRun);
      currentStatus = persistedRun.status;
      if (terminalStatuses.has(currentStatus)) return;
      await new Promise((resolve) => window.setTimeout(resolve, reconnectDelayMs));
    }
  }

  useEffect(() => {
    if (!auth.requestHeaders) return;
    const headers = auth.requestHeaders;
    const savedRunId = window.localStorage.getItem(storageKey);
    if (!savedRunId) return;
    const runId: string = savedRunId;
    let cancelled = false;
    async function restore() {
      try {
        const persistedRun = await readRun(runId, headers);
        if (cancelled) return;
        setRun(persistedRun);
        await subscribeToEvents(runId, headers, persistedRun.status, () => cancelled);
      } catch {
        if (!cancelled) setError("无法恢复该研究任务，请创建新的任务后重试。");
      }
    }
    void restore();
    return () => { cancelled = true; };
  }, [auth.requestHeaders]);

  async function createRun() {
    if (!question.trim() || !auth.requestHeaders) return;
    const headers = auth.requestHeaders;
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/runs`, {
        method: "POST",
        headers: { ...headers, "content-type": "application/json" },
        body: JSON.stringify({ question: question.trim() }),
      });
      if (!response.ok) throw new Error("run_create_failed");
      const created = await response.json() as AgentRun;
      window.localStorage.setItem(storageKey, created.id);
      setEvents([]);
      setError(null);
      setRun(created);
      void subscribeToEvents(created.id, headers, created.status).catch(() => {
        setError("任务已创建，但无法接收实时进度。请刷新页面后重试。");
      });
    } catch {
      setError("无法创建研究任务，请稍后重试。");
    }
  }

  async function cancelRun() {
    if (!run || !auth.requestHeaders) return;
    const headers = auth.requestHeaders;
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/runs/${run.id}/cancel`, {
        method: "POST",
        headers,
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
      <p>任务进度会通过 SSE 实时更新；生产环境由 Redis/Celery Worker 执行并持久化事件。</p>
      {auth.mode === "development" && (
        <p className="development-mode-notice">本地开发身份模式：任务不会调用真实行情或生产模型。</p>
      )}
      {auth.status === "configuration_error" && <p className="error-card" role="alert">{auth.error}</p>}
      {auth.mode === "oidc" && auth.status === "unauthenticated" && <button type="button" onClick={() => void auth.signIn()}>登录后启动研究</button>}
      {auth.mode === "oidc" && auth.status === "authenticated" && <button type="button" onClick={() => void auth.signOut()}>退出登录</button>}
      <label>
        研究问题
        <input value={question} onChange={(event) => setQuestion(event.target.value)} />
      </label>
      <button type="button" onClick={() => void createRun()} disabled={!question.trim() || auth.status !== "authenticated"}>启动研究</button>
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
