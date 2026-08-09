"use client";

import { useEffect, useRef, useState } from "react";

import { useAuth } from "./auth-provider";
import { readAgentEvents, type AgentEvent } from "../lib/sse/agent-events";

type AgentRun = { id: string; status: string; executor_mode: string };

const storageKey = "investment-agent:last-run";
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const terminalStatuses = new Set(["completed", "failed", "cancelled"]);
const reconnectDelayMs = 1_000;
async function readRun(runId: string, headers: HeadersInit, signal: AbortSignal): Promise<AgentRun> {
  const response = await fetch(`${apiBaseUrl}/api/v1/agent/runs/${runId}`, { headers, signal });
  if (!response.ok) throw new Error("run_not_found");
  return response.json() as Promise<AgentRun>;
}

function waitForReconnect(signal: AbortSignal): Promise<boolean> {
  if (signal.aborted) return Promise.resolve(false);
  return new Promise((resolve) => {
    const timeoutId = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve(true);
    }, reconnectDelayMs);
    function onAbort() {
      window.clearTimeout(timeoutId);
      resolve(false);
    }
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

export function AgentRunPanel() {
  const auth = useAuth();
  const [run, setRun] = useState<AgentRun | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const activeSubscription = useRef<AbortController | null>(null);
  const cancelRequest = useRef<AbortController | null>(null);

  function replaceActiveSubscription() {
    activeSubscription.current?.abort();
    const controller = new AbortController();
    activeSubscription.current = controller;
    return controller;
  }

  function releaseSubscription(controller: AbortController) {
    if (activeSubscription.current === controller) activeSubscription.current = null;
  }

  async function subscribeToEvents(runId: string, headers: HeadersInit, initialStatus: string, signal: AbortSignal) {
    let lastEventId = 0;
    let currentStatus = initialStatus;
    while (!signal.aborted) {
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/runs/${runId}/events`, {
        headers: { ...headers, "Last-Event-ID": String(lastEventId) },
        signal,
      });
      if (!response.ok) throw new Error("events_unavailable");
      for await (const event of readAgentEvents(response)) {
        if (signal.aborted) return;
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
      if (signal.aborted || terminalStatuses.has(currentStatus)) return;
      const persistedRun = await readRun(runId, headers, signal);
      if (signal.aborted) return;
      setRun(persistedRun);
      currentStatus = persistedRun.status;
      if (terminalStatuses.has(currentStatus)) return;
      if (!await waitForReconnect(signal)) return;
    }
  }

  useEffect(() => {
    cancelRequest.current?.abort();
    cancelRequest.current = null;
    if (!auth.requestHeaders) return () => {
      activeSubscription.current?.abort();
      activeSubscription.current = null;
      cancelRequest.current?.abort();
      cancelRequest.current = null;
    };
    const headers = auth.requestHeaders;
    const savedRunId = window.localStorage.getItem(storageKey);
    if (!savedRunId) return () => {
      activeSubscription.current?.abort();
      activeSubscription.current = null;
      cancelRequest.current?.abort();
      cancelRequest.current = null;
    };
    const runId: string = savedRunId;
    const controller = replaceActiveSubscription();
    async function restore() {
      try {
        const persistedRun = await readRun(runId, headers, controller.signal);
        if (controller.signal.aborted) return;
        setRun(persistedRun);
        await subscribeToEvents(runId, headers, persistedRun.status, controller.signal);
      } catch {
        if (!controller.signal.aborted) setError("无法恢复该研究任务，请创建新的任务后重试。");
      } finally {
        releaseSubscription(controller);
      }
    }
    void restore();
    return () => {
      activeSubscription.current?.abort();
      activeSubscription.current = null;
      cancelRequest.current?.abort();
      cancelRequest.current = null;
    };
  }, [auth.requestHeaders]);

  async function createRun() {
    if (!question.trim() || !auth.requestHeaders) return;
    const headers = auth.requestHeaders;
    cancelRequest.current?.abort();
    cancelRequest.current = null;
    const controller = replaceActiveSubscription();
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/runs`, {
        method: "POST",
        headers: { ...headers, "content-type": "application/json" },
        body: JSON.stringify({ question: question.trim() }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("run_create_failed");
      const created = await response.json() as AgentRun;
      if (controller.signal.aborted) return;
      window.localStorage.setItem(storageKey, created.id);
      setEvents([]);
      setError(null);
      setRun(created);
      void subscribeToEvents(created.id, headers, created.status, controller.signal)
        .catch(() => {
          if (!controller.signal.aborted) setError("任务已创建，但无法接收实时进度。请刷新页面后重试。");
        })
        .finally(() => releaseSubscription(controller));
    } catch {
      releaseSubscription(controller);
      if (!controller.signal.aborted) setError("无法创建研究任务，请稍后重试。");
    }
  }

  async function cancelRun() {
    if (!run || !auth.requestHeaders) return;
    const headers = auth.requestHeaders;
    cancelRequest.current?.abort();
    const controller = new AbortController();
    cancelRequest.current = controller;
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/runs/${run.id}/cancel`, {
        method: "POST",
        headers,
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("run_cancel_failed");
      const cancelledRun = await response.json() as AgentRun;
      if (controller.signal.aborted) return;
      activeSubscription.current?.abort();
      activeSubscription.current = null;
      setRun(cancelledRun);
    } catch {
      if (!controller.signal.aborted) setError("无法取消研究任务，请稍后重试。");
    } finally {
      if (cancelRequest.current === controller) cancelRequest.current = null;
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
