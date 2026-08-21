"use client";

import { useEffect, useState } from "react";

import { useAuth } from "../../components/auth-provider";

type EvaluationSummary = {
  dataset_version: string;
  mode: string;
  total_cases: number;
  status: "VERIFIED" | "PARTIAL" | "UNVERIFIED";
  metrics: {
    accuracy: number | null;
    citation_score: number | null;
    cost_usd: number | null;
    latency_seconds: number | null;
    tool_success_rate: number | null;
  };
  errors: string[];
  total_research?: number;
  success_rate?: number | null;
  average_latency_seconds?: number | null;
  average_cost_usd?: number | null;
};

type RuntimeEvaluation = {
  source: "agent_runs";
  total_research: number;
  success_rate: number | null;
  average_latency_seconds: number | null;
  average_cost_usd: number | null;
  accuracy: number | null;
  citation_score: number | null;
  tool_success_rate: number | null;
  coverage: Record<string, number>;
};

const metricLabels = [
  ["accuracy", "Accuracy", "事实正确率"],
  ["citation_score", "Citation", "引用覆盖率"],
  ["cost_usd", "Cost", "累计费用"],
  ["latency_seconds", "Latency", "平均响应时间"],
  ["tool_success_rate", "Tool success", "工具调用成功率"],
] as const;

function formatMetric(key: (typeof metricLabels)[number][0], value: number | null): string {
  if (value === null || value === undefined) return "未验证";
  if (key === "cost_usd") return `$${value.toFixed(2)}`;
  if (key === "latency_seconds") return `${value.toFixed(1)}s`;
  return `${Math.round(value * 100)}%`;
}

export default function EvaluationPage() {
  const auth = useAuth();
  const [summary, setSummary] = useState<EvaluationSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
    if (auth.status === "loading") return;
    const headers = auth.requestHeaders ?? undefined;
    fetch(`${baseUrl}/api/v1/evaluation/runtime-summary`, headers ? { headers } : undefined)
      .then(async (runtimeResponse) => {
        if (runtimeResponse.ok) {
          const runtime = await runtimeResponse.json() as RuntimeEvaluation;
          setSummary({
            dataset_version: "live-agent-runs",
            mode: "runtime",
            total_cases: runtime.total_research,
            status: "VERIFIED",
            metrics: {
              accuracy: runtime.accuracy,
              citation_score: runtime.citation_score,
              cost_usd: runtime.average_cost_usd,
              latency_seconds: runtime.average_latency_seconds,
              tool_success_rate: runtime.tool_success_rate,
            },
            total_research: runtime.total_research,
            success_rate: runtime.success_rate,
            average_latency_seconds: runtime.average_latency_seconds,
            average_cost_usd: runtime.average_cost_usd,
            errors: runtime.coverage.accuracy === 0 ? ["Accuracy 需要带标注的评测集，运行时数据暂未提供。"] : [],
          });
          return;
        }
        const response = await fetch(`${baseUrl}/api/v1/evaluation/summary`);
        if (!response.ok) throw new Error("评测摘要暂时不可用");
        setSummary(await response.json() as EvaluationSummary);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "评测摘要暂时不可用"));
  }, [auth.status, auth.requestHeaders]);

  return (
    <main className="page-shell">
      <div className="evaluation-heading">
        <div>
          <p className="eyebrow">Agent Evaluation</p>
          <h1>Research Quality</h1>
          <p className="disclaimer">只展示评测记录中已有证据的指标；缺少真实运行记录时不会填充示例分数。</p>
        </div>
        {summary && <span className={`evaluation-status evaluation-status--${summary.status.toLowerCase()}`}>{summary.status}</span>}
      </div>

      {error && <p className="error-card">{error}</p>}
      {!summary && !error && <p className="empty-state">正在读取评测摘要…</p>}
      {summary && (
        <>
          <section aria-label="研究质量指标" className="evaluation-grid">
            <article className="evaluation-card" key="total-research">
              <p>Total Research</p>
              <strong>{summary.total_research ?? summary.total_cases}</strong>
              <small>研究任务总数</small>
            </article>
            <article className="evaluation-card" key="success-rate">
              <p>Success Rate</p>
              <strong>{summary.success_rate == null ? "未验证" : `${Math.round(summary.success_rate * 100)}%`}</strong>
              <small>任务完成率</small>
            </article>
            <article className="evaluation-card" key="average-latency">
              <p>Average Latency</p>
              <strong>{summary.average_latency_seconds == null ? "未验证" : `${summary.average_latency_seconds.toFixed(1)}s`}</strong>
              <small>平均响应时间</small>
            </article>
            <article className="evaluation-card" key="average-cost">
              <p>Average Cost</p>
              <strong>{summary.average_cost_usd == null ? "未验证" : `$${summary.average_cost_usd.toFixed(2)}`}</strong>
              <small>每次研究平均成本</small>
            </article>
            {metricLabels.map(([key, label, description]) => (
              <article className="evaluation-card" key={key}>
                <p>{label}</p>
                <strong>{formatMetric(key, summary.metrics[key])}</strong>
                <small>{description}</small>
              </article>
            ))}
          </section>
          <section className="evaluation-meta">
            <span>数据集：{summary.dataset_version}</span>
            <span>样本：{summary.total_cases}</span>
            <span>模式：{summary.mode}</span>
          </section>
          {summary.errors.length > 0 && <p className="evaluation-note">评测备注：{summary.errors.join("；")}</p>}
        </>
      )}
    </main>
  );
}
