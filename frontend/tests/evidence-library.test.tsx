import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const authRequestHeaders = vi.hoisted(() => ({
  "X-Development-Principal-ID": "analyst-1",
  "X-Development-Workspace-ID": "workspace-a",
}));

vi.mock("../components/auth-provider", () => ({
  useAuth: () => ({ status: "authenticated", mode: "development", requestHeaders: authRequestHeaders }),
}));

import { EvidenceLibrary } from "../components/evidence-library";

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("evidence library", () => {
  it("uploads a researcher-selected file and renders versioned page citations from search", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({
        id: "00000000-0000-0000-0000-000000000021",
        filename: "重大资产重组报告书.pdf",
        symbol: "600519",
        document_type: "announcement",
        source_url: "https://example.com/a.pdf",
        version: 1,
        status: "ready",
        page_count: 12,
        parsed_block_count: 24,
      }, 201))
      .mockResolvedValueOnce(response({
        results: [{
          evidence_id: "document:21:block:7",
          document_id: "00000000-0000-0000-0000-000000000021",
          document_version: 1,
          filename: "重大资产重组报告书.pdf",
          source_url: "https://example.com/a.pdf",
          page_number: 8,
          block_id: "7",
          text: "本次交易对价为 10 亿元。",
          parser: "native",
          confidence: 1,
        }],
      }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<EvidenceLibrary />);

    await user.type(screen.getByLabelText("股票代码"), "600519");
    await user.upload(screen.getByLabelText("公告或研报文件"), new File(["pdf"], "重大资产重组报告书.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "上传并解析" }));

    expect(await screen.findByText("已建立证据版本")).toBeInTheDocument();
    expect(screen.getByText(/v1 · 12 页 · 24 个文本块/)).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toContain("filename=%E9%87%8D");

    await user.type(screen.getByLabelText("在已上传材料中检索"), "交易对价");
    await user.click(screen.getByRole("button", { name: "检索证据" }));

    expect(await screen.findByText("本次交易对价为 10 亿元。")).toBeInTheDocument();
    expect(screen.getByText("重大资产重组报告书.pdf · v1 · 第 8 页 · 块 7")).toBeInTheDocument();
  });

  it("marks a file without a trusted text layer as needing OCR instead of making a citation", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({
      id: "00000000-0000-0000-0000-000000000022",
      filename: "扫描公告.pdf",
      symbol: "600519",
      document_type: "announcement",
      source_url: null,
      version: 1,
      status: "needs_ocr",
      page_count: 4,
      parsed_block_count: 0,
    }, 201)));
    const user = userEvent.setup();
    render(<EvidenceLibrary />);

    await user.type(screen.getByLabelText("股票代码"), "600519");
    await user.upload(screen.getByLabelText("公告或研报文件"), new File(["pdf"], "扫描公告.pdf"));
    await user.click(screen.getByRole("button", { name: "上传并解析" }));

    expect(await screen.findByText(/未提取到可信文字层/)).toBeInTheDocument();
  });

  it("renders a fixed transaction fact table with source pages and no inferred values", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({
        id: "00000000-0000-0000-0000-000000000023",
        filename: "收购公告.pdf",
        symbol: "600519",
        document_type: "announcement",
        source_url: null,
        version: 3,
        status: "ready",
        page_count: 10,
        parsed_block_count: 20,
      }, 201))
      .mockResolvedValueOnce(response({
        document_id: "00000000-0000-0000-0000-000000000023",
        filename: "收购公告.pdf",
        document_version: 3,
        rows: [
          { field: "交易对价", value: "已在公告原文中披露", evidence: [{ page_number: 8, block_id: "7", text: "本次交易对价为 10 亿元。" }] },
          { field: "资金来源", value: "公告未披露", evidence: [] },
        ],
        boundary: "仅展示公告原文和页码。",
      }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<EvidenceLibrary />);

    await user.type(screen.getByLabelText("股票代码"), "600519");
    await user.upload(screen.getByLabelText("公告或研报文件"), new File(["pdf"], "收购公告.pdf"));
    await user.click(screen.getByRole("button", { name: "上传并解析" }));
    await user.click(await screen.findByRole("button", { name: "生成交易事实表" }));

    expect(await screen.findByRole("table", { name: "交易事实表" })).toBeInTheDocument();
    expect(screen.getByText("本次交易对价为 10 亿元。")).toBeInTheDocument();
    expect(screen.getByText("第 8 页")).toBeInTheDocument();
    expect(screen.getByText("公告未披露")).toBeInTheDocument();
    expect(fetchMock.mock.calls[1]?.[0]).toContain("/documents/00000000-0000-0000-0000-000000000023/transaction-facts");
  });

  it("shows recomputable market-reaction inputs, benchmarks, dates, and the non-causal boundary", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({
        id: "00000000-0000-0000-0000-000000000024", filename: "收购公告.pdf", symbol: "600519",
        document_type: "announcement", source_url: null, version: 1, status: "ready", page_count: 10, parsed_block_count: 20,
      }, 201))
      .mockResolvedValueOnce(response({
        symbol: "600519", announcement_date: "2025-01-26", event_date: "2025-01-27", event_window: [-20, 20],
        benchmark_indices: [{ name: "沪深300", symbol: "000300", source: "AkShare" }, { name: "申万行业", symbol: "801010", source: "AkShare" }],
        formula: "区间收益率(%) = 100 × (期末收盘价 ÷ 期初收盘价 − 1)",
        before_after_change: { before_date: "2025-01-24", event_date: "2025-01-27", after_date: "2025-01-28", before_to_event_return_percent: 1, event_to_after_return_percent: 2 },
        window_result: { start_offset: -20, end_offset: 20, start_date: "2024-12-20", end_date: "2025-02-20", stock_start_close: 10, stock_end_close: 11, csi_300_start_close: 1000, csi_300_end_close: 1010, industry_start_close: 2000, industry_end_close: 2010, stock_return_percent: 10, csi_300_return_percent: 1, industry_return_percent: 0.5, excess_vs_csi_300_percentage_points: 9, excess_vs_industry_percentage_points: 9.5 },
        volume_volatility_change: { pre_period: "[-20, -1]", post_period: "[0, +20]", pre_average_volume: 100, post_average_volume: 120, volume_change_percent: 20, pre_daily_volatility_percent: 1, post_daily_volatility_percent: 2, volatility_change_percentage_points: 1 },
        market_dates: [{ event_offset: 0, market_date: "2025-01-27", stock_close: 10.5, stock_volume: 110, csi_300_close: 1005, industry_index_close: 2005 }],
        missing_trading_dates: ["2025-01-26"], missing_trading_dates_definition: "任一序列缺少观测", source: "AkShare", boundary: "不将变化归因于公告。",
      }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<EvidenceLibrary />);

    await user.type(screen.getByLabelText("股票代码"), "600519");
    await user.upload(screen.getByLabelText("公告或研报文件"), new File(["pdf"], "收购公告.pdf"));
    await user.click(screen.getByRole("button", { name: "上传并解析" }));
    await user.type(await screen.findByLabelText("公告日期"), "2025-01-26");
    await user.type(screen.getByLabelText("行业指数代码"), "801010");
    await user.type(screen.getByLabelText("行业指数名称"), "申万行业");
    await user.click(screen.getByRole("button", { name: "计算 [-20, +20] 市场反应" }));

    expect(await screen.findByRole("table", { name: "事件窗口收益率" })).toBeInTheDocument();
    expect(screen.getByText(/沪深300（000300）；申万行业（801010）/)).toBeInTheDocument();
    expect(screen.getByText("2025-01-26")).toBeInTheDocument();
    expect(screen.getByText("不将变化归因于公告。")).toBeInTheDocument();
    expect(fetchMock.mock.calls[1]?.[0]).toContain("/documents/00000000-0000-0000-0000-000000000024/market-reaction");
  });
});
