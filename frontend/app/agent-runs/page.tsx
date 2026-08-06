import { AgentRunPanel } from "../../components/agent-run-panel";

export default function AgentRunsPage() {
  return (
    <main className="page-shell">
      <h1>研究任务</h1>
      <p className="disclaimer">研究输出仅作辅助，不构成投资建议或收益承诺。</p>
      <AgentRunPanel />
    </main>
  );
}
