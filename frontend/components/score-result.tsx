import type { ScoringResponse } from "../lib/api/types";

export function ScoreResult({ response }: { response: ScoringResponse }) {
  if (response.status === "insufficient_data") {
    return (
      <section className="result-card" aria-live="polite">
        <h2>数据不足，暂不提供评分</h2>
        <p>{`覆盖率：${Math.round(response.coverage * 100)}%`}</p>
        <p>缺失核心维度：{response.missing_core_dimensions.join("、") || "无"}</p>
        <p>缺失指标：{response.missing_metrics.join("、") || "无"}</p>
      </section>
    );
  }

  return (
    <section className="result-card" aria-live="polite">
      <h2>评分结果</h2>
      <p className="total">总分 <strong>{response.result.total}</strong></p>
      <p>评级：{response.result.grade}</p>
      <p>{`结论：${response.result.label}`}</p>
      <h3>维度详情</h3>
      {response.result.dimensions.map((dimension) => (
        <article className="dimension" key={dimension.name}>
          <h4>{dimension.name}：{dimension.score}</h4>
          <ul>
            {dimension.metrics.map((metric) => (
              <li key={metric.name}>{metric.name}：{metric.value}，子分 {metric.subscore}</li>
            ))}
          </ul>
        </article>
      ))}
    </section>
  );
}
