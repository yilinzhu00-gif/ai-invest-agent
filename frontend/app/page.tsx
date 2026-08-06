import Link from "next/link";

export default function HomePage() {
  return (
    <main className="page-shell">
      <h1>投研评分助手</h1>
      <p>输入可验证的财务与市场指标，查看已有评分服务返回的结构化结果。</p>
      <Link className="button-link" href="/scoring">前往评分</Link>
      <Link className="button-link" href="/agent-runs">查看研究任务</Link>
    </main>
  );
}
