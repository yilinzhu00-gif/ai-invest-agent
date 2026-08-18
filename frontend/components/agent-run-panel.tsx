"use client";

import { useEffect, useRef, useState } from "react";

import { useAuth } from "./auth-provider";
import { readAgentEvents, type AgentEvent } from "../lib/sse/agent-events";

type AgentRun = { id: string; status: string; executor_mode: string };
type DailyClose = { date: string; close: number };
type MarketSnapshot = {
  symbol: string;
  as_of_date: string;
  close: number;
  change_percent?: number | null;
  high?: number | null;
  low?: number | null;
  volume?: number | null;
  turnover?: number | null;
  period_change_percent?: number | null;
  recent_closes: DailyClose[];
};
type ResearchResult = {
  symbol: string;
  summary: string;
  snapshot: MarketSnapshot;
  source: string;
  boundary: string;
};

const storageKey = "investment-agent:last-run";
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const terminalStatuses = new Set(["completed", "failed", "cancelled", "rejected"]);
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

function renderEvent(event: AgentEvent): string {
  if (typeof event.data.text === "string") return event.data.text;
  const verdict = typeof event.data.verdict === "string" ? event.data.verdict : null;
  const errorCode = typeof event.data.error_code === "string" ? event.data.error_code : null;
  const labels: Record<string, string> = {
    "agent.analyst.started": "Analyst：正在根据证据撰写草稿",
    "agent.analyst.completed": "Analyst：草稿已完成",
    "agent.validator.started": "Validator：正在执行引用与数值校验",
    "agent.validator.completed": event.data.passed === true ? "Validator：校验通过" : "Validator：校验未通过",
    "agent.reviewer.started": "Reviewer：正在独立审核证据支持关系",
    "agent.reviewer.completed": verdict ? `Reviewer：审核结论为 ${verdict}` : "Reviewer：审核完成",
    "agent.reviewer.skipped": "Reviewer：因 Validator 拒绝而跳过",
    "agent.flow.revision_scheduled": "流程：已安排一次定向修订",
    "agent.flow.human_review": "流程：需要人工复核",
    "run.awaiting_confirmation": "流程：等待人工确认；确认后才会保存可复用记忆",
    "memory.saved": "Memory：已保存本次经人工确认的研究摘要",
    "run.recovery_required": "任务失败：可从已持久化的输入和事件记录恢复",
    "research.result": "研究结果：已生成可引用的市场快照",
  };
  if (event.event === "run.failed" && errorCode) {
    return errorCode === "market_data_unavailable"
      ? "任务失败：暂时无法取得公开行情，请稍后恢复任务重试。"
      : `任务失败：${errorCode}`;
  }
  return labels[event.event] ?? event.event;
}

function parseResearchResult(event: AgentEvent): ResearchResult | null {
  if (event.event !== "research.result") return null;
  const { data } = event;
  const snapshot = data.snapshot;
  if (
    typeof data.symbol !== "string" ||
    typeof data.summary !== "string" ||
    typeof data.source !== "string" ||
    typeof data.boundary !== "string" ||
    !snapshot || typeof snapshot !== "object" || Array.isArray(snapshot)
  ) return null;
  const parsed = snapshot as Record<string, unknown>;
  if (
    typeof parsed.symbol !== "string" ||
    typeof parsed.as_of_date !== "string" ||
    typeof parsed.close !== "number" ||
    !Array.isArray(parsed.recent_closes) ||
    !parsed.recent_closes.every((item) => (
      item && typeof item === "object" && !Array.isArray(item)
      && typeof (item as Record<string, unknown>).date === "string"
      && typeof (item as Record<string, unknown>).close === "number"
    ))
  ) return null;
  return {
    symbol: data.symbol,
    summary: data.summary,
    source: data.source,
    boundary: data.boundary,
    snapshot: {
      ...parsed,
      symbol: parsed.symbol,
      as_of_date: parsed.as_of_date,
      close: parsed.close,
      recent_closes: parsed.recent_closes as DailyClose[],
    } as MarketSnapshot,
  };
}

function numberLabel(value: number | null | undefined, suffix = ""): string {
  return typeof value === "number" ? `${value.toLocaleString("zh-CN")}${suffix}` : "未提供";
}

export function AgentRunPanel() {
  const auth = useAuth();
  const [run, setRun] = useState<AgentRun | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [symbol, setSymbol] = useState("");
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
          const parsedResult = parseResearchResult(event);
          if (parsedResult) setResult(parsedResult);
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
        body: JSON.stringify({ question: question.trim(), symbol: symbol.trim() }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("run_create_failed");
      const created = await response.json() as AgentRun;
      if (controller.signal.aborted) return;
      window.localStorage.setItem(storageKey, created.id);
      setEvents([]);
      setResult(null);
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

  async function confirmRun(decision: "approve" | "reject") {
    if (!run || !auth.requestHeaders) return;
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/runs/${run.id}/confirm`, {
        method: "POST",
        headers: { ...auth.requestHeaders, "content-type": "application/json" },
        body: JSON.stringify({ decision }),
      });
      if (!response.ok) throw new Error("run_confirmation_failed");
      setRun(await response.json() as AgentRun);
    } catch {
      setError("无法提交人工确认，请稍后重试。");
    }
  }

  async function recoverRun() {
    if (!run || !auth.requestHeaders) return;
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/runs/${run.id}/recover`, {
        method: "POST",
        headers: auth.requestHeaders,
      });
      if (!response.ok) throw new Error("run_recovery_failed");
      const recovered = await response.json() as AgentRun;
      setRun(recovered);
      const controller = replaceActiveSubscription();
      void subscribeToEvents(recovered.id, auth.requestHeaders, recovered.status, controller.signal)
        .catch(() => {
          if (!controller.signal.aborted) setError("任务已恢复，但无法接收实时进度。请刷新页面后重试。");
        })
        .finally(() => releaseSubscription(controller));
    } catch {
      setError("无法恢复该任务，请稍后重试。");
    }
  }

  return (
    <section className="agent-run-panel" aria-label="研究任务">
      <h2>研究任务</h2>
      <p>任务进度会通过 SSE 实时更新；生产环境由 Redis/Celery Worker 执行并持久化事件。</p>
      {auth.mode === "development" && (
        <p className="development-mode-notice">本地开发身份模式：会读取公开日线行情快照，但不会调用生产模型。</p>
      )}
      {auth.status === "configuration_error" && <p className="error-card" role="alert">{auth.error}</p>}
      {auth.mode === "oidc" && auth.status === "unauthenticated" && <button type="button" onClick={() => void auth.signIn()}>登录后启动研究</button>}
      {auth.mode === "oidc" && auth.status === "authenticated" && <button type="button" onClick={() => void auth.signOut()}>退出登录</button>}
      <label>
        股票代码
        <input
          inputMode="numeric"
          maxLength={6}
          pattern="[0-9]{6}"
          placeholder="例如 600519"
          value={symbol}
          onChange={(event) => setSymbol(event.target.value.replace(/\D/g, ""))}
        />
      </label>
      <label>
        研究问题
        <input value={question} onChange={(event) => setQuestion(event.target.value)} />
      </label>
      <button type="button" onClick={() => void createRun()} disabled={!question.trim() || !/^\d{6}$/.test(symbol) || auth.status !== "authenticated"}>启动研究</button>
      {run && <p>状态：{run.status}</p>}
      {run && !terminalStatuses.has(run.status) && (
        <button type="button" onClick={() => void cancelRun()}>取消任务</button>
      )}
      {run?.status === "awaiting_confirmation" && (
        <p>
          <button type="button" onClick={() => void confirmRun("approve")}>确认并保存 Memory</button>
          <button type="button" onClick={() => void confirmRun("reject")}>拒绝本次结果</button>
        </p>
      )}
      {run?.status === "failed" && (
        <button type="button" onClick={() => void recoverRun()}>从持久化记录恢复</button>
      )}
      {error && <p className="error-card" role="alert">{error}</p>}
      {result && (
        <section className="research-result" aria-label="研究结果">
          <h3>研究结果</h3>
          <p>{result.summary}</p>
          <h4>市场快照：{result.symbol}（截至 {result.snapshot.as_of_date}）</h4>
          <dl className="market-snapshot">
            <div><dt>最近收盘价</dt><dd>{numberLabel(result.snapshot.close)}</dd></div>
            <div><dt>当日涨跌幅</dt><dd>{numberLabel(result.snapshot.change_percent, "%")}</dd></div>
            <div><dt>近 {result.snapshot.recent_closes.length} 个交易日变动</dt><dd>{numberLabel(result.snapshot.period_change_percent, "%")}</dd></div>
            <div><dt>当日最高 / 最低</dt><dd>{numberLabel(result.snapshot.high)} / {numberLabel(result.snapshot.low)}</dd></div>
            <div><dt>成交量 / 成交额</dt><dd>{numberLabel(result.snapshot.volume)} / {numberLabel(result.snapshot.turnover)}</dd></div>
          </dl>
          <h4>最近交易日收盘价</h4>
          <ul className="recent-closes">
            {result.snapshot.recent_closes.map((item) => <li key={item.date}>{item.date}：{numberLabel(item.close)}</li>)}
          </ul>
          <p className="result-source">来源：{result.source}</p>
          <p className="disclaimer">{result.boundary}</p>
        </section>
      )}
      {events.map((event, index) => (
        <p key={`${event.id ?? "heartbeat"}-${index}`} className="agent-event">
          {renderEvent(event)}
        </p>
      ))}
    </section>
  );
}
