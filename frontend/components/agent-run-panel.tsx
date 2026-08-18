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
type EvidenceCitation = {
  evidence_id: string;
  filename: string;
  document_version: number;
  page_number: number;
  block_id: string;
};
type EvidenceResearchResult = {
  status: "supported" | "human_review" | "insufficient_evidence";
  summary: string;
  claims: { text: string; citations: EvidenceCitation[] }[];
  conclusion: {
    sections: { title: string; claims: { text: string; citations: EvidenceCitation[] }[] }[];
    missing_information: string[];
    confidence: "high" | "medium" | "low";
    confidence_rationale: string;
  } | null;
  boundary: string;
};
type BriefCitation = EvidenceCitation;
type BriefClaim = { text: string; citations: BriefCitation[] };
type BriefContent = {
  title: string;
  summary: string;
  data_date: string;
  sections: { title: string; claims: BriefClaim[] }[];
  missing_information: string[];
  confidence: "high" | "medium" | "low";
  confidence_rationale: string;
  risk_disclaimer: string;
};
type BriefVersion = { version: number; content: BriefContent; content_sha256: string };

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
  if (event.event === "research.evidence_result") {
    if (event.data.status === "insufficient_evidence") return "研究结果：未找到可直接支持该问题的证据";
    if (event.data.status === "human_review") return "研究结果：已找到相关原文，等待人工审核";
    return "研究结果：已生成可引用的证据结论";
  }
  const verdict = typeof event.data.verdict === "string" ? event.data.verdict : null;
  const errorCode = typeof event.data.error_code === "string" ? event.data.error_code : null;
  const labels: Record<string, string> = {
    "agent.analyst.started": "Analyst：正在根据证据撰写草稿",
    "agent.analyst.completed": "Analyst：草稿已完成",
    "agent.numeric_validator.started": "数值校验器：正在执行引用与计算校验",
    "agent.numeric_validator.completed": event.data.passed === true ? "数值校验器：校验通过" : "数值校验器：校验未通过",
    "agent.reviewer.started": "Reviewer：正在独立审核证据支持关系",
    "agent.reviewer.completed": verdict ? `Reviewer：审核结论为 ${verdict}` : "Reviewer：审核完成",
    "agent.reviewer.skipped": "Reviewer：因数值校验器拒绝而跳过",
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

function parseEvidenceResearchResult(event: AgentEvent): EvidenceResearchResult | null {
  if (event.event !== "research.evidence_result") return null;
  const { data } = event;
  if (
    (data.status !== "supported" && data.status !== "human_review" && data.status !== "insufficient_evidence")
    || typeof data.summary !== "string"
    || typeof data.boundary !== "string"
    || !Array.isArray(data.claims)
  ) return null;
  const claims = data.claims.map((claim) => {
    if (!claim || typeof claim !== "object" || Array.isArray(claim)) return null;
    const value = claim as Record<string, unknown>;
    if (typeof value.text !== "string" || !Array.isArray(value.citations)) return null;
    const citations = value.citations.map((citation) => {
      if (!citation || typeof citation !== "object" || Array.isArray(citation)) return null;
      const item = citation as Record<string, unknown>;
      if (
        typeof item.evidence_id !== "string" || typeof item.filename !== "string"
        || typeof item.document_version !== "number" || typeof item.page_number !== "number"
        || typeof item.block_id !== "string"
      ) return null;
      return item as EvidenceCitation;
    });
    if (citations.some((citation) => citation === null)) return null;
    return { text: value.text, citations: citations as EvidenceCitation[] };
  });
  if (claims.some((claim) => claim === null)) return null;
  let conclusion: EvidenceResearchResult["conclusion"] = null;
  if (data.conclusion !== null && data.conclusion !== undefined) {
    if (!data.conclusion || typeof data.conclusion !== "object" || Array.isArray(data.conclusion)) return null;
    const raw = data.conclusion as Record<string, unknown>;
    const expectedTitles = ["已证实的交易事实", "公告后的市场反应", "可能的影响机制", "正面因素", "风险和不确定性"];
    if (!Array.isArray(raw.sections) || !Array.isArray(raw.missing_information)
      || !raw.missing_information.every((item) => typeof item === "string")
      || (raw.confidence !== "high" && raw.confidence !== "medium" && raw.confidence !== "low")
      || typeof raw.confidence_rationale !== "string") return null;
    const sections = raw.sections.map((section) => {
      if (!section || typeof section !== "object" || Array.isArray(section)) return null;
      const value = section as Record<string, unknown>;
      if (typeof value.title !== "string" || !Array.isArray(value.claims)) return null;
      const sectionClaims = value.claims.map((claim) => {
        if (!claim || typeof claim !== "object" || Array.isArray(claim)) return null;
        const item = claim as Record<string, unknown>;
        if (typeof item.text !== "string" || !Array.isArray(item.citations)) return null;
        const citations = item.citations.map((citation) => {
          if (!citation || typeof citation !== "object" || Array.isArray(citation)) return null;
          const citationValue = citation as Record<string, unknown>;
          if (typeof citationValue.evidence_id !== "string" || typeof citationValue.filename !== "string"
            || typeof citationValue.document_version !== "number" || typeof citationValue.page_number !== "number"
            || typeof citationValue.block_id !== "string") return null;
          return citationValue as EvidenceCitation;
        });
        if (citations.some((citation) => citation === null)) return null;
        return { text: item.text, citations: citations as EvidenceCitation[] };
      });
      if (sectionClaims.some((claim) => claim === null)) return null;
      return { title: value.title, claims: sectionClaims as { text: string; citations: EvidenceCitation[] }[] };
    });
    if (sections.some((section) => section === null)
      || sections.map((section) => section?.title).join("|") !== expectedTitles.join("|")) return null;
    conclusion = {
      sections: sections as NonNullable<EvidenceResearchResult["conclusion"]>["sections"],
      missing_information: raw.missing_information as string[],
      confidence: raw.confidence as "high" | "medium" | "low",
      confidence_rationale: raw.confidence_rationale as string,
    };
  }
  return {
    status: data.status,
    summary: data.summary,
    claims: claims as { text: string; citations: EvidenceCitation[] }[],
    conclusion,
    boundary: data.boundary,
  };
}

function numberLabel(value: number | null | undefined, suffix = ""): string {
  return typeof value === "number" ? `${value.toLocaleString("zh-CN")}${suffix}` : "未提供";
}

function briefFromEvidenceResult(result: EvidenceResearchResult): BriefContent | null {
  if (!result.conclusion) return null;
  return {
    title: "研究简报",
    summary: result.summary,
    data_date: "",
    sections: result.conclusion.sections,
    missing_information: result.conclusion.missing_information,
    confidence: result.conclusion.confidence,
    confidence_rationale: result.conclusion.confidence_rationale,
    risk_disclaimer: "本简报仅基于所列来源和数据日期整理，不构成投资建议。",
  };
}

export function AgentRunPanel({ documentId, documentType, requireDocument = false }: {
  documentId?: string;
  documentType?: "announcement" | "research_report" | "other";
  requireDocument?: boolean;
}) {
  const auth = useAuth();
  const [run, setRun] = useState<AgentRun | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [evidenceResult, setEvidenceResult] = useState<EvidenceResearchResult | null>(null);
  const [briefDraft, setBriefDraft] = useState<BriefContent | null>(null);
  const [briefVersion, setBriefVersion] = useState<number | null>(null);
  const [briefHistory, setBriefHistory] = useState<BriefVersion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [symbol, setSymbol] = useState("");
  const activeSubscription = useRef<AbortController | null>(null);
  const cancelRequest = useRef<AbortController | null>(null);
  const asksForForecast = /预测|预计|目标价|盈利预期|估值/.test(question);

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
          const parsedEvidenceResult = parseEvidenceResearchResult(event);
          if (parsedEvidenceResult) setEvidenceResult(parsedEvidenceResult);
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

  useEffect(() => {
    const draft = evidenceResult ? briefFromEvidenceResult(evidenceResult) : null;
    if (draft) setBriefDraft(draft);
  }, [evidenceResult]);

  useEffect(() => {
    if (!run || !evidenceResult || !auth.requestHeaders) return;
    const controller = new AbortController();
    const runId = run.id;
    const headers = auth.requestHeaders;
    async function loadHistory() {
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/runs/${runId}/brief/versions`, {
        headers,
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("brief_history_unavailable");
      const history = await response.json() as BriefVersion[];
      if (controller.signal.aborted) return;
      setBriefHistory(history);
      setBriefVersion(history.at(-1)?.version ?? null);
    }
    void loadHistory().catch(() => {
      if (!controller.signal.aborted) setError("无法读取研究简报历史，请稍后重试。");
    });
    return () => controller.abort();
  }, [auth.requestHeaders, evidenceResult, run]);

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
        body: JSON.stringify({
          question: question.trim(),
          symbol: symbol.trim(),
          document_id: documentId,
        }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("run_create_failed");
      const created = await response.json() as AgentRun;
      if (controller.signal.aborted) return;
      window.localStorage.setItem(storageKey, created.id);
      setEvents([]);
      setResult(null);
      setEvidenceResult(null);
      setBriefDraft(null);
      setBriefVersion(null);
      setBriefHistory([]);
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

  async function saveBriefVersion(): Promise<number | null> {
    if (!run || !briefDraft || !auth.requestHeaders) return null;
    if (!briefDraft.data_date) {
      setError("导出前请填写数据日期，避免把生成日期误当作数据日期。");
      return null;
    }
    const response = await fetch(`${apiBaseUrl}/api/v1/agent/runs/${run.id}/brief/versions`, {
      method: "POST",
      headers: { ...auth.requestHeaders, "content-type": "application/json" },
      body: JSON.stringify({ content: briefDraft }),
    });
    if (!response.ok) {
      setError("无法保存研究简报版本，请检查固定分区、引用和数据日期。");
      return null;
    }
    const saved = await response.json() as BriefVersion;
    setBriefVersion(saved.version);
    setBriefHistory((existing) => [...existing.filter((item) => item.version !== saved.version), saved]);
    return saved.version;
  }

  async function decideBrief(decision: "accept" | "reject") {
    if (!run || !auth.requestHeaders) return;
    const version = await saveBriefVersion();
    if (version === null) return;
    const response = await fetch(
      `${apiBaseUrl}/api/v1/agent/runs/${run.id}/brief/versions/${version}/decision`,
      {
        method: "POST",
        headers: { ...auth.requestHeaders, "content-type": "application/json" },
        body: JSON.stringify({ decision }),
      },
    );
    if (!response.ok) {
      setError("无法记录研究员的接受/驳回决定。");
      return;
    }
    await confirmRun(decision === "accept" ? "approve" : "reject");
  }

  async function downloadBrief(exportFormat: "markdown" | "pdf" | "docx") {
    if (!run || !briefVersion || !auth.requestHeaders) return;
    const response = await fetch(
      `${apiBaseUrl}/api/v1/agent/runs/${run.id}/brief/versions/${briefVersion}/export/${exportFormat}`,
      { headers: auth.requestHeaders },
    );
    if (!response.ok) {
      setError("无法导出研究简报。");
      return;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `research-brief-v${briefVersion}.${exportFormat === "markdown" ? "md" : exportFormat}`;
    anchor.click();
    URL.revokeObjectURL(url);
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
        <textarea
          rows={3}
          maxLength={4000}
          placeholder="自由描述你想核对、比较或研究的问题，例如：研报对 2025 年净利润的预测是多少？"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
        />
      </label>
      {requireDocument && <p className="document-selection-note">问题可自由输入。系统会先检索相关原文；只有原文直接支持的部分才会进入结论，不会用行情、记忆或常识补全。</p>}
      {requireDocument && asksForForecast && documentType === "announcement" && <p className="evidence-guidance">这是预测 / 估值类问题。当前选中的是公告，仍可启动检索，但若要得到可采纳的预测结论，请补充包含预测表或目标价的研报、业绩预告等材料。</p>}
      <button type="button" onClick={() => void createRun()} disabled={!question.trim() || !/^\d{6}$/.test(symbol) || (requireDocument && !documentId) || auth.status !== "authenticated"}>启动研究</button>
      {run && <p>状态：{run.status}</p>}
      {run && !terminalStatuses.has(run.status) && (
        <button type="button" onClick={() => void cancelRun()}>取消任务</button>
      )}
      {run?.status === "awaiting_confirmation" && (
        <p>
          <button type="button" onClick={() => void (briefDraft ? decideBrief("accept") : confirmRun("approve"))}>接受 Agent 观点并确认</button>
          <button type="button" onClick={() => void (briefDraft ? decideBrief("reject") : confirmRun("reject"))}>驳回 Agent 观点</button>
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
      {evidenceResult && (
        <section className={evidenceResult.status === "insufficient_evidence" ? "missing-evidence" : "research-result"} aria-label="公告证据研究结果">
          <h3>公告证据研究结果</h3>
          {evidenceResult.status === "human_review" && <p>已找到可引用原文，但系统不会把“相关原文”自动当作问题的完整答案；请人工审核后再采纳。</p>}
          <p>{evidenceResult.summary}</p>
          {(evidenceResult.conclusion?.sections ?? [{ title: "已证实的交易事实", claims: evidenceResult.claims }]).map((section) => (
            <section key={section.title} className="conclusion-section">
              <h4>{section.title}</h4>
              {section.claims.length === 0 ? <p>尚缺少可引用证据。</p> : section.claims.map((claim, index) => (
                <article key={`${claim.text}-${index}`} className="evidence-claim">
                  <p>{claim.text}</p>
                  <ul>
                    {claim.citations.map((citation) => (
                      <li key={citation.evidence_id}>{citation.filename} · v{citation.document_version} · 第 {citation.page_number} 页 · 块 {citation.block_id}</li>
                    ))}
                  </ul>
                </article>
              ))}
            </section>
          ))}
          {evidenceResult.conclusion && <>
            <h4>尚缺少的信息</h4>
            <ul>{evidenceResult.conclusion.missing_information.map((item) => <li key={item}>{item}</li>)}</ul>
            <h4>结论置信度</h4>
            <p>{evidenceResult.conclusion.confidence}：{evidenceResult.conclusion.confidence_rationale}</p>
          </>}
          <p className="disclaimer">{evidenceResult.boundary}</p>
        </section>
      )}
      {briefDraft && run && (
        <section className="research-brief-editor" aria-label="研究简报编辑与导出">
          <h3>研究员修改、确认和导出</h3>
          <label>
            简报标题
            <input value={briefDraft.title} onChange={(event) => setBriefDraft({ ...briefDraft, title: event.target.value })} />
          </label>
          <label>
            数据日期
            <input type="date" value={briefDraft.data_date} onChange={(event) => setBriefDraft({ ...briefDraft, data_date: event.target.value })} />
          </label>
          <label>
            摘要
            <textarea value={briefDraft.summary} onChange={(event) => setBriefDraft({ ...briefDraft, summary: event.target.value })} />
          </label>
          {briefDraft.sections.map((section, sectionIndex) => (
            <section key={section.title} className="brief-edit-section">
              <h4>{section.title}</h4>
              {section.claims.length === 0 && <p>尚缺少可引用证据。</p>}
              {section.claims.map((claim, claimIndex) => (
                <article key={`${section.title}-${claimIndex}`}>
                  <textarea
                    aria-label={`${section.title} 第 ${claimIndex + 1} 条结论`}
                    value={claim.text}
                    onChange={(event) => setBriefDraft({
                      ...briefDraft,
                      sections: briefDraft.sections.map((current, currentIndex) => (
                        currentIndex !== sectionIndex
                          ? current
                          : { ...current, claims: current.claims.map((currentClaim, currentClaimIndex) => currentClaimIndex !== claimIndex ? currentClaim : { ...currentClaim, text: event.target.value }) }
                      )),
                    })}
                  />
                  <ul>{claim.citations.map((citation) => <li key={citation.evidence_id}>{citation.filename} · v{citation.document_version} · 第 {citation.page_number} 页 · 块 {citation.block_id}</li>)}</ul>
                </article>
              ))}
            </section>
          ))}
          <label>
            尚缺少的信息（每行一项）
            <textarea value={briefDraft.missing_information.join("\n")} onChange={(event) => setBriefDraft({ ...briefDraft, missing_information: event.target.value.split("\n").map((item) => item.trim()).filter(Boolean) })} />
          </label>
          <label>
            结论置信度
            <select value={briefDraft.confidence} onChange={(event) => setBriefDraft({ ...briefDraft, confidence: event.target.value as BriefContent["confidence"] })}>
              <option value="high">high</option><option value="medium">medium</option><option value="low">low</option>
            </select>
          </label>
          <label>
            置信度说明
            <textarea value={briefDraft.confidence_rationale} onChange={(event) => setBriefDraft({ ...briefDraft, confidence_rationale: event.target.value })} />
          </label>
          <label>
            风险声明
            <textarea value={briefDraft.risk_disclaimer} onChange={(event) => setBriefDraft({ ...briefDraft, risk_disclaimer: event.target.value })} />
          </label>
          <p><button type="button" onClick={() => void saveBriefVersion()}>保存修改历史</button></p>
          {briefVersion && <p>当前已保存版本：v{briefVersion}</p>}
          {briefHistory.length > 0 && <p>已保存历史：{briefHistory.map((item) => `v${item.version}`).join("、")}</p>}
          {briefVersion && <p>
            <button type="button" onClick={() => void downloadBrief("markdown")}>导出 Markdown</button>
            <button type="button" onClick={() => void downloadBrief("pdf")}>导出 PDF</button>
            <button type="button" onClick={() => void downloadBrief("docx")}>导出 Word</button>
          </p>}
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
