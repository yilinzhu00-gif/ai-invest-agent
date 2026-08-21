"use client";

import { useEffect, useState } from "react";

import { useAuth } from "./auth-provider";
import { AgentRunPanel } from "./agent-run-panel";

type EvidenceDocument = {
  id: string;
  filename: string;
  version: number;
  status: string;
  symbol: string | null;
  page_count: number;
  document_type: "financial_report" | "announcement" | "research_report" | "broker_report" | "industry_report" | "policy" | "other";
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function ResearchTaskWorkspace() {
  const auth = useAuth();
  const [documents, setDocuments] = useState<EvidenceDocument[]>([]);
  const [documentId, setDocumentId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const selectedDocument = documents.find((document) => document.id === documentId);

  useEffect(() => {
    if (!auth.requestHeaders) return;
    const headers = auth.requestHeaders;
    let active = true;
    async function loadDocuments() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/documents`, { headers });
        if (!response.ok) throw new Error("documents_unavailable");
        const loaded = await response.json() as EvidenceDocument[];
        if (!active) return;
        const ready = loaded.filter((document) => document.status === "ready");
        setDocuments(ready);
        setDocumentId((selected) => ready.some((document) => document.id === selected) ? selected : (ready[0]?.id ?? ""));
      } catch {
        if (active) setError("无法读取已上传的证据文档。请返回证据库检查后重试。");
      }
    }
    void loadDocuments();
    return () => { active = false; };
  }, [auth.requestHeaders]);

  return (
    <>
      <section className="document-picker" aria-label="选择研究证据">
        <h2>选择研究证据</h2>
        <label>
          已上传公告 / 研报
          <select value={documentId} onChange={(event) => setDocumentId(event.target.value)} disabled={!documents.length}>
            {documents.length === 0 && <option value="">暂无可用文档</option>}
            {documents.map((document) => <option key={document.id} value={document.id}>{document.filename} · {documentTypeLabel(document.document_type)} · v{document.version} · {document.page_count} 页</option>)}
          </select>
        </label>
        {selectedDocument && <p className="document-selection-note">当前材料：{documentTypeGuidance(selectedDocument.document_type)}。</p>}
        {!documents.length && !error && <p className="missing-evidence">请先在“上传公告 / 研报”中建立可检索证据。</p>}
        {error && <p className="error-card" role="alert">{error}</p>}
      </section>
      <AgentRunPanel
        documentId={documentId || undefined}
        documentType={selectedDocument?.document_type}
        requireDocument
      />
    </>
  );
}

function documentTypeLabel(type: EvidenceDocument["document_type"]): string {
  return {
    financial_report: "财报 / 年报",
    announcement: "公告",
    research_report: "研报",
    broker_report: "券商研报",
    industry_report: "行业报告",
    policy: "政策文件",
    other: "其他材料",
  }[type];
}

function documentTypeGuidance(type: EvidenceDocument["document_type"]): string {
  if (type === "announcement") return "公告，可用于核对已披露事实";
  if (type === "financial_report") return "财报 / 年报，可用于核对经营、财务与风险披露";
  if (type === "broker_report" || type === "research_report") return "研报，可用于核对明确披露的预测与观点";
  if (type === "industry_report") return "行业报告，可用于核对竞争格局与行业趋势";
  if (type === "policy") return "政策文件，可用于核对政策约束与影响";
  return "其他材料，请先核对其是否直接覆盖你的问题";
}
