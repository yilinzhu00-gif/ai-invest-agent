import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const authRequestHeaders = vi.hoisted(() => ({
  "X-Development-Principal-ID": "analyst-1",
  "X-Development-Workspace-ID": "workspace-a",
}));

vi.mock("../components/auth-provider", () => ({
  useAuth: () => ({ status: "authenticated", mode: "development", requestHeaders: authRequestHeaders }),
}));

import { AgentRunPanel } from "../components/agent-run-panel";
import { ResearchTaskWorkspace } from "../components/research-task-workspace";

function response(body: unknown, status = 200, contentType = "application/json") {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status,
    headers: { "content-type": contentType },
  });
}

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("research task evidence selection", () => {
  it("lists ready documents and carries the selected document ID into the run", async () => {
    const documentId = "00000000-0000-0000-0000-000000000031";
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response([{
        id: documentId,
        filename: "收购报告书.pdf",
        version: 2,
        status: "ready",
        symbol: "600519",
        page_count: 12,
        document_type: "announcement",
      }]))
      .mockResolvedValueOnce(response({ id: "00000000-0000-0000-0000-000000000041", status: "queued", executor_mode: "development_only", document_id: documentId }, 202))
      .mockResolvedValueOnce(response("event: heartbeat\ndata: {}\n\n", 200, "text/event-stream"))
      .mockResolvedValueOnce(response({ id: "00000000-0000-0000-0000-000000000041", status: "completed", executor_mode: "development_only", document_id: documentId }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ResearchTaskWorkspace />);

    expect(await screen.findByRole("option", { name: "收购报告书.pdf · 公告 · v2 · 12 页" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("股票代码"), "600519");
    await user.type(screen.getByLabelText("研究问题"), "交易对价是多少");
    await user.click(screen.getByRole("button", { name: "启动研究" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toMatchObject({
      document_id: documentId,
      question: "交易对价是多少",
    });
  });

  it("keeps forecast questions available while explaining when the selected material is an announcement", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response([{
      id: "00000000-0000-0000-0000-000000000031",
      filename: "半年度报告.pdf",
      version: 1,
      status: "ready",
      symbol: "002396",
      page_count: 151,
      document_type: "announcement",
    }])));
    const user = userEvent.setup();
    render(<ResearchTaskWorkspace />);

    await user.type(await screen.findByLabelText("股票代码"), "002396");
    await user.type(await screen.findByLabelText("研究问题"), "研报对 2025 年净利润的预测是多少？");

    expect(screen.getByText(/问题可自由输入/)).toBeInTheDocument();
    expect(screen.getByText(/当前选中的是公告/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "启动研究" })).toBeEnabled();
  });

  it("replays persisted document citations after refresh", async () => {
    const runId = "00000000-0000-0000-0000-000000000041";
    localStorage.setItem("investment-agent:last-run", runId);
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(response({ id: runId, status: "completed", executor_mode: "development_only" }))
      .mockResolvedValueOnce(response(
        "id: 1\nevent: research.evidence_result\ndata: {\"status\":\"supported\",\"summary\":\"已找到直接证据。\",\"claims\":[{\"text\":\"本次交易对价为 10 亿元。\",\"citations\":[{\"evidence_id\":\"document:31:block:7\",\"filename\":\"收购报告书.pdf\",\"document_version\":2,\"page_number\":8,\"block_id\":\"7\"}]}],\"boundary\":\"仅整理公告文本。\"}\n\n",
        200,
        "text/event-stream",
      )));

    render(<AgentRunPanel documentId="00000000-0000-0000-0000-000000000031" requireDocument />);

    expect(await screen.findByText("本次交易对价为 10 亿元。")).toBeInTheDocument();
    expect(screen.getByText("收购报告书.pdf · v2 · 第 8 页 · 块 7")).toBeInTheDocument();
  });

  it("renders the fixed evidence-grounded conclusion partitions", async () => {
    const runId = "00000000-0000-0000-0000-000000000042";
    localStorage.setItem("investment-agent:last-run", runId);
    const citation = {
      evidence_id: "document:31:block:7",
      filename: "收购报告书.pdf",
      document_version: 2,
      page_number: 8,
      block_id: "7",
    };
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(response({ id: runId, status: "completed", executor_mode: "development_only" }))
      .mockResolvedValueOnce(response(
        `id: 1\nevent: research.evidence_result\ndata: ${JSON.stringify({
          status: "supported",
          summary: "基于公告证据形成待人工复核的研究结论。",
          claims: [{ text: "本次交易对价为 10 亿元。", citations: [citation] }],
          conclusion: {
            sections: [
              { title: "已证实的交易事实", claims: [{ text: "本次交易对价为 10 亿元。", citations: [citation] }] },
              { title: "公告后的市场反应", claims: [] },
              { title: "可能的影响机制", claims: [] },
              { title: "正面因素", claims: [] },
              { title: "风险和不确定性", claims: [] },
            ],
            missing_information: ["公告后行情窗口尚未绑定。"],
            confidence: "low",
            confidence_rationale: "仅有一处关键公告证据。",
          },
          boundary: "每条结论仅整理所列公告文本。",
        })}\n\n`,
        200,
        "text/event-stream",
      )));

    render(<AgentRunPanel documentId="00000000-0000-0000-0000-000000000031" requireDocument />);

    expect(await screen.findByText("已证实的交易事实")).toBeInTheDocument();
    expect(screen.getAllByText("公告后的市场反应")).not.toHaveLength(0);
    expect(screen.getAllByText("可能的影响机制")).not.toHaveLength(0);
    expect(screen.getAllByText("正面因素")).not.toHaveLength(0);
    expect(screen.getAllByText("风险和不确定性")).not.toHaveLength(0);
    expect(screen.getByText("尚缺少的信息")).toBeInTheDocument();
    expect(screen.getAllByText("结论置信度")).not.toHaveLength(0);
  });

  it("saves the researcher edit with the same citation version used for export", async () => {
    const runId = "00000000-0000-0000-0000-000000000043";
    localStorage.setItem("investment-agent:last-run", runId);
    const citation = { evidence_id: "document:31:block:7", filename: "收购报告书.pdf", document_version: 2, page_number: 8, block_id: "7" };
    const conclusion = {
      sections: [
        { title: "已证实的交易事实", claims: [{ text: "交易对价为 10 亿元。", citations: [citation] }] },
        { title: "公告后的市场反应", claims: [] }, { title: "可能的影响机制", claims: [] },
        { title: "正面因素", claims: [] }, { title: "风险和不确定性", claims: [] },
      ],
      missing_information: ["公告后数据。"], confidence: "low", confidence_rationale: "引用有限。",
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ id: runId, status: "completed", executor_mode: "development_only" }))
      .mockResolvedValueOnce(response(`id: 1\nevent: research.evidence_result\ndata: ${JSON.stringify({ status: "human_review", summary: "交易对价为 10 亿元。", claims: conclusion.sections[0].claims, conclusion, boundary: "仅整理公告文本。" })}\n\n`, 200, "text/event-stream"))
      .mockResolvedValueOnce(response([]))
      .mockResolvedValueOnce(response({ version: 1, content: { title: "研究简报", summary: "交易对价为 12 亿元。", data_date: "2026-08-18", sections: conclusion.sections, missing_information: conclusion.missing_information, confidence: "low", confidence_rationale: "引用有限。", risk_disclaimer: "本简报仅基于所列来源和数据日期整理，不构成投资建议。" }, content_sha256: "a".repeat(64) }, 201));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<AgentRunPanel documentId="00000000-0000-0000-0000-000000000031" requireDocument />);
    const dateInput = await screen.findByLabelText("数据日期");
    await user.type(dateInput, "2026-08-18");
    const claimInput = screen.getByLabelText("已证实的交易事实 第 1 条结论");
    await user.clear(claimInput);
    await user.type(claimInput, "交易对价为 12 亿元。");
    await user.click(screen.getByRole("button", { name: "保存修改历史" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    const body = JSON.parse(fetchMock.mock.calls[3]?.[1]?.body as string);
    expect(body.content.data_date).toBe("2026-08-18");
    expect(body.content.sections[0].claims[0].text).toBe("交易对价为 12 亿元。");
    expect(body.content.sections[0].claims[0].citations).toEqual([citation]);
  });
});
