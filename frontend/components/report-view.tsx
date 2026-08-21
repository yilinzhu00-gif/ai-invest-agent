import Link from "next/link";
import { REPORT } from "../lib/research-data";

export function ReportView() {
  return (
    <main className="product-shell report-shell">
      <div className="report-breadcrumb"><Link href="/">Dashboard</Link><span>/</span><span>Report View</span></div>
      <section className="report-hero"><div><div className="report-title-row"><span className="report-ticker">{REPORT.symbol}</span><span className="report-stance">{REPORT.stance}</span></div><h1>{REPORT.name}</h1><p>{REPORT.subtitle}</p></div><div className="report-score"><span>研究评分</span><strong>{REPORT.score}</strong><small>/ 10 · 中高置信度</small></div></section>
      <div className="report-meta"><span>最后更新 {REPORT.asOf}</span><span>·</span><span>演示研究报告</span><Link href="/research-chat">继续追问 ↗</Link></div>
      <section className="metric-row">{REPORT.metrics.map((metric) => <div className="metric-card" key={metric.label}><span>{metric.label}</span><strong>{metric.value}</strong><small className={`metric-detail metric-detail--${metric.tone}`}>{metric.detail}</small></div>)}</section>
      <div className="report-columns"><div className="report-main-column"><ReportSection title="投资逻辑" eyebrow="THESIS"><ol className="numbered-list">{REPORT.investmentLogic.map((item) => <li key={item}>{item}</li>)}</ol></ReportSection><ReportSection title="财务分析" eyebrow="FUNDAMENTALS"><div className="financial-grid">{REPORT.financials.map((item) => <div key={item.label}><span>{item.label}</span><strong>{item.value}</strong><small>{item.note}</small></div>)}</div><p className="analysis-note">现金流质量是本报告的核心观察项。收入增长并不激进，但高毛利服务业务和回购政策提升了每股价值的可见度。</p></ReportSection><ReportSection title="风险" eyebrow="RISKS"><ul className="risk-list">{REPORT.risks.map((item) => <li key={item}>{item}</li>)}</ul></ReportSection></div><aside className="report-side-column"><section className="scenario-card"><div className="scenario-heading"><span className="scenario-dot scenario-dot--bull" /><h2>Bull case</h2></div><p>服务与 AI 共同带来第二增长曲线。</p><ul>{REPORT.bull.map((item) => <li key={item}>{item}</li>)}</ul></section><section className="scenario-card"><div className="scenario-heading"><span className="scenario-dot scenario-dot--bear" /><h2>Bear case</h2></div><p>盈利保持增长，但估值与需求不匹配。</p><ul>{REPORT.bear.map((item) => <li key={item}>{item}</li>)}</ul></section><section className="source-card"><h2>引用来源</h2>{REPORT.sources.map((source, index) => <div className="source-row" key={source.label}><span className="source-index">0{index + 1}</span><div><strong>{source.label}</strong><small>{source.detail}</small></div></div>)}<p className="source-boundary">每个判断都应回到原始披露和数据日期核验。</p></section></aside></div>
      <p className="demo-disclaimer">演示报告 · 数值和结论用于展示 Report View 信息架构，不构成投资建议。</p>
    </main>
  );
}

function ReportSection({ title, eyebrow, children }: { title: string; eyebrow: string; children: React.ReactNode }) {
  return <section className="report-section"><p className="section-label">{eyebrow}</p><h2>{title}</h2>{children}</section>;
}
