import Link from "next/link";
import { WATCHLIST } from "../lib/research-data";

export function DashboardView() {
  return (
    <main className="product-shell dashboard-shell">
      <section className="dashboard-hero">
        <div>
          <p className="product-kicker">INVESTMENT RESEARCH / 07</p>
          <h1>早上好，研究员。</h1>
          <p className="dashboard-hero-copy">把市场噪音收敛成可追踪的投资判断。</p>
        </div>
        <div className="market-status"><span className="status-dot" /> 美股盘前 · 08:30 ET</div>
      </section>

      <section className="dashboard-section-head">
        <div><p className="section-label">WATCHLIST</p><h2>股票池</h2></div>
        <span className="muted-text">3 个标的 · 更新于今日</span>
      </section>
      <section className="stock-grid" aria-label="股票池">
        {WATCHLIST.map((stock) => (
          <article className="stock-card" key={stock.symbol}>
            <div className="stock-card-top"><div><span className="ticker">{stock.symbol}</span><span className="stock-name">{stock.name}</span></div><span className={`change change--${stock.tone}`}>{stock.change}</span></div>
            <div className="stock-price">{stock.price}</div>
            <div className="stock-sparkline" aria-hidden="true"><span /><span /><span /><span /><span /><span /><span /></div>
            <p className="stock-thesis">{stock.thesis}</p>
            <div className="stock-card-bottom"><span>{stock.sector}</span><span>{stock.updated}</span></div>
          </article>
        ))}
      </section>

      <section className="dashboard-lower-grid">
        <article className="action-card action-card--dark"><div><p className="section-label section-label--light">RESEARCH CHAT</p><h2>把问题交给研究助手</h2><p>用自然语言追问估值、财务和风险，答案会以流式方式逐字返回。</p></div><Link className="product-button product-button--light" href="/research-chat">开始对话 <span>↗</span></Link></article>
        <article className="action-card"><div><p className="section-label">LATEST REPORT</p><h2>AAPL · 生态型现金流复利</h2><p>一页查看投资逻辑、财务分析、风险和多空情景。</p></div><Link className="text-link" href="/reports">打开报告 →</Link></article>
      </section>
      <p className="demo-disclaimer">演示工作区 · 行情与研究内容为界面演示数据，不构成投资建议。</p>
    </main>
  );
}
