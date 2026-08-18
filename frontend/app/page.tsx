import Link from "next/link";

export default function HomePage() {
  return (
    <main className="page-shell research-overview">
      <section className="overview-hero">
        <p className="eyebrow">研究工作流</p>
        <h1>从来源证据到可导出的研究简报</h1>
        <p>先建立可引用的公告或研报，再发起研究任务，由研究员确认后保存、导出。</p>
        <Link className="button-link" href="/evidence">从上传证据开始</Link>
      </section>

      <section aria-label="研究主链路" className="workflow-grid">
        <article className="workflow-card">
          <p className="workflow-step">第一步</p>
          <h2>建立证据库</h2>
          <p>上传公告或研报，保留文件版本、页码和可检索文本，先确认材料状态为 ready。</p>
          <Link href="/evidence">进入证据库 →</Link>
        </article>
        <article className="workflow-card">
          <p className="workflow-step">第二步</p>
          <h2>发起研究任务</h2>
          <p>选择一份证据、填写研究问题；系统只使用命中的原文生成带引用的结论。</p>
          <Link href="/agent-runs">进入研究任务 →</Link>
        </article>
        <article className="workflow-card">
          <p className="workflow-step">第三步</p>
          <h2>人工确认与导出</h2>
          <p>研究员修改结论、接受或驳回观点，保存不可变版本后导出 Markdown、PDF 或 Word。</p>
          <Link href="/agent-runs">查看待审核任务 →</Link>
        </article>
      </section>

      <section className="overview-secondary">
        <div>
          <h2>独立工具：股票评分</h2>
          <p>评分页用于手工输入可验证指标，不会替代公告或研报的证据引用。</p>
        </div>
        <Link className="button-link button-link--secondary" href="/scoring">前往股票评分</Link>
      </section>
    </main>
  );
}
