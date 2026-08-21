"use client";

import { FormEvent, useState } from "react";

import { useAuth } from "./auth-provider";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const researchTypes = [
  ["investment_value", "投资价值分析"],
  ["financial", "财务分析"],
  ["industry", "行业研究"],
  ["competitive", "竞争分析"],
  ["risk", "风险分析"],
] as const;

const depths = [["quick", "Quick"], ["standard", "Standard"], ["deep_research", "Deep Research"]] as const;

export function ResearchCreateForm() {
  const auth = useAuth();
  const [target, setTarget] = useState("NVDA");
  const [researchType, setResearchType] = useState("investment_value");
  const [timeRange, setTimeRange] = useState("recent_1y");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [depth, setDepth] = useState("standard");
  const [outputFormat, setOutputFormat] = useState("markdown");
  const [status, setStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!auth.requestHeaders) return;
    setStatus("submitting");
    setMessage("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/research/tasks`, {
        method: "POST",
        headers: { ...auth.requestHeaders, "content-type": "application/json" },
        body: JSON.stringify({
          target,
          research_type: researchType,
          depth,
          time_range: timeRange,
          output_format: outputFormat,
          ...(timeRange === "custom" ? { custom_start: customStart, custom_end: customEnd } : {}),
        }),
      });
      if (!response.ok) throw new Error("research_task_create_failed");
      const created = await response.json() as { id: string };
      window.localStorage.setItem("investment-agent:last-run", created.id);
      setStatus("success");
      setMessage(`任务已创建：${created.id}`);
    } catch {
      setStatus("error");
      setMessage("无法创建研究任务，请检查配置后重试。");
    }
  }

  if (auth.status === "configuration_error") return <p className="error-card" role="alert">{auth.error}</p>;
  if (auth.mode === "oidc" && auth.status === "unauthenticated") {
    return <button type="button" onClick={() => void auth.signIn()}>登录后创建研究任务</button>;
  }

  return (
    <form className="research-create-form" onSubmit={(event) => void submit(event)}>
      <div className="research-create-grid">
        <label>研究标的
          <select aria-label="研究标的" value={target} onChange={(event) => setTarget(event.target.value)}>
            <option value="NVDA">NVDA · NVIDIA</option>
            <option value="AAPL">AAPL · Apple</option>
            <option value="TSMC">TSMC · 台积电</option>
          </select>
        </label>
        <label>研究类型
          <select aria-label="研究类型" value={researchType} onChange={(event) => setResearchType(event.target.value)}>
            {researchTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>时间范围
          <select aria-label="时间范围" value={timeRange} onChange={(event) => setTimeRange(event.target.value)}>
            <option value="recent_1y">最近一年</option>
            <option value="recent_3y">最近三年</option>
            <option value="custom">自定义</option>
          </select>
        </label>
        <label>研究深度
          <select aria-label="研究深度" value={depth} onChange={(event) => setDepth(event.target.value)}>
            {depths.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>输出格式
          <select aria-label="输出格式" value={outputFormat} onChange={(event) => setOutputFormat(event.target.value)}>
            <option value="markdown">Markdown</option>
            <option value="pdf">PDF</option>
            <option value="ppt">PPT</option>
          </select>
        </label>
      </div>
      {timeRange === "custom" && <div className="research-custom-range">
        <label>开始日期<input aria-label="开始日期" type="date" value={customStart} onChange={(event) => setCustomStart(event.target.value)} required /></label>
        <label>结束日期<input aria-label="结束日期" type="date" value={customEnd} onChange={(event) => setCustomEnd(event.target.value)} required /></label>
      </div>}
      <div className="research-create-actions">
        <button type="submit" disabled={status === "submitting" || auth.status !== "authenticated"}>{status === "submitting" ? "创建中…" : "创建研究任务"}</button>
        {message && <p className={status === "error" ? "error-card" : "success-note"} role={status === "error" ? "alert" : undefined}>{message}</p>}
      </div>
    </form>
  );
}
