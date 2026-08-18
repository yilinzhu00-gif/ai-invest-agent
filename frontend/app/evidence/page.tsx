import { EvidenceLibrary } from "../../components/evidence-library";

export default function EvidencePage() {
  return (
    <main className="page-shell">
      <h1>并购 / 重大事项证据库</h1>
      <p className="disclaimer">本页只处理来源材料与引用定位，不生成影响判断、收益率或投资结论。</p>
      <EvidenceLibrary />
    </main>
  );
}
