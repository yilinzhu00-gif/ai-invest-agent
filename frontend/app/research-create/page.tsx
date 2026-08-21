import { ResearchCreateForm } from "../../components/research-create-form";
import { MemoryProfileForm } from "../../components/memory-profile-form";

export default function ResearchCreatePage() {
  return (
    <main className="page-shell">
      <h1>创建研究任务</h1>
      <p className="disclaimer">配置研究标的、范围和深度后，系统会创建可追踪的 Agent Research Run。</p>
      <ResearchCreateForm />
      <MemoryProfileForm />
    </main>
  );
}
