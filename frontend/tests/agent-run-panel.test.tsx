import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const authRequestHeaders = vi.hoisted(() => ({
  Authorization: "Bearer access-token",
  "X-Workspace-ID": "workspace-a",
}));

vi.mock("../components/auth-provider", () => ({
  useAuth: () => ({
    status: "authenticated",
    mode: "oidc",
    requestHeaders: authRequestHeaders,
    error: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
  }),
}));

import { AgentRunPanel } from "../components/agent-run-panel";

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

describe("agent run panel", () => {
  it("restores the saved run after refresh and renders persisted SSE events", async () => {
    localStorage.setItem("investment-agent:last-run", "00000000-0000-0000-0000-000000000001");
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(
          response({
            id: "00000000-0000-0000-0000-000000000001",
            status: "completed",
            executor_mode: "development_only",
          }),
        )
        .mockResolvedValueOnce(
          response(
            "id: 1\nevent: text.delta\ndata: {\"text\":\"开发执行器已完成持久化事件演示。\"}\n\nevent: heartbeat\ndata: {}\n\n",
            200,
            "text/event-stream",
          ),
        ),
    );

    render(<AgentRunPanel />);

    expect(await screen.findByText("开发执行器已完成持久化事件演示。")).toBeInTheDocument();
    expect(screen.getByText("状态：completed")).toBeInTheDocument();
  });

  it("creates a run and saves its ID for a later refresh", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response({
          id: "00000000-0000-0000-0000-000000000002",
          status: "queued",
          executor_mode: "development_only",
        }, 202),
      ),
    );
    const user = userEvent.setup();

    render(<AgentRunPanel />);
    await user.type(screen.getByLabelText("股票代码"), "600519");
    await user.type(screen.getByLabelText("研究问题"), "总结贵州茅台的估值风险");
    await user.click(screen.getByRole("button", { name: "启动研究" }));

    expect(await screen.findByText("状态：queued")).toBeInTheDocument();
    expect(localStorage.getItem("investment-agent:last-run")).toBe("00000000-0000-0000-0000-000000000002");
  });

  it("subscribes to SSE immediately after creating a run", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(response({
          id: "00000000-0000-0000-0000-000000000004",
          status: "queued",
          executor_mode: "development_only",
        }, 202))
        .mockResolvedValueOnce(response(
          "id: 1\nevent: text.delta\ndata: {\"text\":\"研究已完成\"}\n\n",
          200,
          "text/event-stream",
        )),
    );
    const user = userEvent.setup();

    render(<AgentRunPanel />);
    await user.type(screen.getByLabelText("股票代码"), "600519");
    await user.type(screen.getByLabelText("研究问题"), "上证指数走势");
    await user.click(screen.getByRole("button", { name: "启动研究" }));

    expect(await screen.findByText("研究已完成")).toBeInTheDocument();
  });

  it("renders the persisted Analyst, numeric validator, and Reviewer stages", async () => {
    localStorage.setItem("investment-agent:last-run", "00000000-0000-0000-0000-000000000005");
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(response({
          id: "00000000-0000-0000-0000-000000000005",
          status: "completed",
          executor_mode: "development_only",
        }))
        .mockResolvedValueOnce(response(
          "id: 1\nevent: agent.analyst.started\ndata: {\"revision\":0}\n\n"
          + "id: 2\nevent: agent.numeric_validator.completed\ndata: {\"passed\":true,\"error_count\":0}\n\n"
          + "id: 3\nevent: agent.reviewer.completed\ndata: {\"verdict\":\"approve\"}\n\n",
          200,
          "text/event-stream",
        )),
    );

    render(<AgentRunPanel />);

    expect(await screen.findByText("Analyst：正在根据证据撰写草稿")).toBeInTheDocument();
    expect(screen.getByText("数值校验器：校验通过")).toBeInTheDocument();
    expect(screen.getByText("Reviewer：审核结论为 approve")).toBeInTheDocument();
  });

  it("renders a citable market result card instead of leaving the snapshot in the event log", async () => {
    localStorage.setItem("investment-agent:last-run", "00000000-0000-0000-0000-000000000012");
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(response({
          id: "00000000-0000-0000-0000-000000000012",
          status: "completed",
          executor_mode: "development_only",
          symbol: "600519",
        }))
        .mockResolvedValueOnce(response(
          "id: 1\nevent: research.result\ndata: {\"symbol\":\"600519\",\"summary\":\"基于已提供证据整理。\",\"source\":\"AkShare stock_zh_a_hist (Eastmoney)\",\"boundary\":\"不预测未来走势。\",\"snapshot\":{\"symbol\":\"600519\",\"as_of_date\":\"2026-08-12\",\"close\":1472.5,\"change_percent\":0.86,\"high\":1480,\"low\":1462,\"volume\":120,\"turnover\":1200,\"period_change_percent\":1.55,\"recent_closes\":[{\"date\":\"2026-08-11\",\"close\":1460},{\"date\":\"2026-08-12\",\"close\":1472.5}]}}\n\n",
          200,
          "text/event-stream",
        )),
    );

    render(<AgentRunPanel />);

    expect(await screen.findByRole("region", { name: "研究结果" })).toBeInTheDocument();
    expect(screen.getByText("市场快照：600519（截至 2026-08-12）")).toBeInTheDocument();
    expect(screen.getByText("1,472.5")).toBeInTheDocument();
    expect(screen.getByText("不预测未来走势。")).toBeInTheDocument();
  });

  it("creates a market debate run and renders Bull, Bear, and Moderator events", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({
        id: "00000000-0000-0000-0000-000000000013",
        status: "queued",
        executor_mode: "development_only",
        workflow: "market_debate",
        symbol: "600519",
      }, 202))
      .mockResolvedValueOnce(response(
        "id: 1\nevent: debate.bull\ndata: {\"role\":\"bull\",\"core_thesis\":\"估值数据提供支持。\",\"claims\":[{\"text\":\"价格观测已取得。\",\"evidence_refs\":[\"quote.quotes[0].price\"]}]}\n\n"
        + "id: 2\nevent: debate.bear\ndata: {\"role\":\"bear\",\"core_thesis\":\"财务期间仍需核验。\",\"claims\":[{\"text\":\"报告期较短。\",\"evidence_refs\":[\"financials.report_period\"]}]}\n\n"
        + "id: 3\nevent: debate.moderator\ndata: {\"consensus\":[\"共享底稿\"],\"disagreements\":[\"数据完整性\"],\"verification_checklist\":[\"补充数据\"],\"data_gaps\":[]}\n\n",
        200,
        "text/event-stream",
      ));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<AgentRunPanel />);
    await user.selectOptions(screen.getByLabelText("任务类型"), "market_debate");
    await user.type(screen.getByLabelText("股票代码"), "600519");
    await user.type(screen.getByLabelText("研究问题"), "整理支持与风险");
    await user.click(screen.getByRole("button", { name: "启动研究" }));

    expect(await screen.findByRole("region", { name: "市场事实辩论" })).toBeInTheDocument();
    expect(screen.getByText("Bull：支持因素")).toBeInTheDocument();
    expect(screen.getByText("Bear：风险与反证")).toBeInTheDocument();
    expect(screen.getByText("Moderator：共识、分歧与核验")).toBeInTheDocument();
    const createRequest = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(String(createRequest.body))).toMatchObject({ workflow: "market_debate", symbol: "600519" });
  });

  it("reconnects after a running snapshot and resumes after the last event", async () => {
    const runId = "00000000-0000-0000-0000-000000000006";
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({
        id: runId,
        status: "queued",
        executor_mode: "development_only",
      }, 202))
      .mockResolvedValueOnce(response(
        "id: 1\nevent: text.delta\ndata: {\"text\":\"第一阶段\"}\n\nevent: heartbeat\ndata: {}\n\n",
        200,
        "text/event-stream",
      ))
      .mockResolvedValueOnce(response({ id: runId, status: "running", executor_mode: "development_only" }))
      .mockResolvedValueOnce(response(
        "id: 1\nevent: text.delta\ndata: {\"text\":\"第一阶段\"}\n\nid: 2\nevent: text.delta\ndata: {\"text\":\"研究已完成\"}\n\n",
        200,
        "text/event-stream",
      ))
      .mockResolvedValueOnce(response({ id: runId, status: "completed", executor_mode: "development_only" }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<AgentRunPanel />);
    await user.type(screen.getByLabelText("股票代码"), "600519");
    await user.type(screen.getByLabelText("研究问题"), "持续追踪研究任务");
    await user.click(screen.getByRole("button", { name: "启动研究" }));

    expect(await screen.findByText("状态：completed", {}, { timeout: 2_000 })).toBeInTheDocument();
    expect(screen.getAllByText("第一阶段")).toHaveLength(1);
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      headers: expect.objectContaining({ "Last-Event-ID": "0" }),
    });
    expect(fetchMock.mock.calls[3]?.[1]).toMatchObject({
      headers: expect.objectContaining({ "Last-Event-ID": "1" }),
    });
  });

  it("stops the previous create subscription when a new run starts", async () => {
    const firstRunId = "00000000-0000-0000-0000-000000000007";
    const secondRunId = "00000000-0000-0000-0000-000000000008";
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ id: firstRunId, status: "queued", executor_mode: "development_only" }, 202))
      .mockResolvedValueOnce(response("event: heartbeat\ndata: {}\n\n", 200, "text/event-stream"))
      .mockResolvedValueOnce(response({ id: firstRunId, status: "running", executor_mode: "development_only" }))
      .mockResolvedValueOnce(response({ id: secondRunId, status: "queued", executor_mode: "development_only" }, 202))
      .mockResolvedValueOnce(response(
        "id: 1\nevent: text.delta\ndata: {\"text\":\"新任务已完成\"}\n\n",
        200,
        "text/event-stream",
      ))
      .mockResolvedValueOnce(response({ id: secondRunId, status: "completed", executor_mode: "development_only" }))
      .mockResolvedValueOnce(response(
        "id: 2\nevent: text.delta\ndata: {\"text\":\"旧任务迟到事件\"}\n\n",
        200,
        "text/event-stream",
      ))
      .mockResolvedValueOnce(response({ id: firstRunId, status: "completed", executor_mode: "development_only" }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<AgentRunPanel />);
    await user.type(screen.getByLabelText("股票代码"), "600519");
    await user.type(screen.getByLabelText("研究问题"), "第一个任务");
    await user.click(screen.getByRole("button", { name: "启动研究" }));
    expect(await screen.findByText("状态：running")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("研究问题"));
    await user.type(screen.getByLabelText("研究问题"), "第二个任务");
    await user.click(screen.getByRole("button", { name: "启动研究" }));

    expect(await screen.findByText("新任务已完成")).toBeInTheDocument();
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 1_100));
    });
    expect(screen.queryByText("旧任务迟到事件")).not.toBeInTheDocument();
    expect(localStorage.getItem("investment-agent:last-run")).toBe(secondRunId);
  });

  it("ignores a stale cancel response after a new run starts", async () => {
    const firstRunId = "00000000-0000-0000-0000-000000000009";
    const secondRunId = "00000000-0000-0000-0000-000000000010";
    let resolveCancel!: (value: Response) => void;
    const delayedCancel = new Promise<Response>((resolve) => {
      resolveCancel = resolve;
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ id: firstRunId, status: "running", executor_mode: "development_only" }))
      .mockResolvedValueOnce(response("event: heartbeat\ndata: {}\n\n", 200, "text/event-stream"))
      .mockResolvedValueOnce(response({ id: firstRunId, status: "running", executor_mode: "development_only" }))
      .mockReturnValueOnce(delayedCancel)
      .mockResolvedValueOnce(response({ id: secondRunId, status: "queued", executor_mode: "development_only" }, 202))
      .mockResolvedValueOnce(response(
        "id: 1\nevent: text.delta\ndata: {\"text\":\"新任务结果\"}\n\n",
        200,
        "text/event-stream",
      ))
      .mockResolvedValueOnce(response({ id: secondRunId, status: "completed", executor_mode: "development_only" }));
    vi.stubGlobal("fetch", fetchMock);
    localStorage.setItem("investment-agent:last-run", firstRunId);
    const user = userEvent.setup();

    render(<AgentRunPanel />);
    await user.click(await screen.findByRole("button", { name: "取消任务" }));
    await user.type(screen.getByLabelText("股票代码"), "600519");
    await user.type(screen.getByLabelText("研究问题"), "新任务");
    await user.click(screen.getByRole("button", { name: "启动研究" }));
    expect(await screen.findByText("状态：completed")).toBeInTheDocument();

    await act(async () => {
      resolveCancel(response({ id: firstRunId, status: "cancelled", executor_mode: "development_only" }));
      await new Promise((resolve) => window.setTimeout(resolve, 0));
    });

    expect(screen.getByText("状态：completed")).toBeInTheDocument();
    expect(screen.queryByText("状态：cancelled")).not.toBeInTheDocument();
    expect(localStorage.getItem("investment-agent:last-run")).toBe(secondRunId);
  });

  it("keeps tracking the run after cancellation fails", async () => {
    const runId = "00000000-0000-0000-0000-000000000011";
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ id: runId, status: "running", executor_mode: "development_only" }))
      .mockResolvedValueOnce(response("event: heartbeat\ndata: {}\n\n", 200, "text/event-stream"))
      .mockResolvedValueOnce(response({ id: runId, status: "running", executor_mode: "development_only" }))
      .mockResolvedValueOnce(response({ detail: "cancel failed" }, 500))
      .mockResolvedValueOnce(response(
        "id: 1\nevent: text.delta\ndata: {\"text\":\"原任务继续完成\"}\n\n",
        200,
        "text/event-stream",
      ))
      .mockResolvedValueOnce(response({ id: runId, status: "completed", executor_mode: "development_only" }));
    vi.stubGlobal("fetch", fetchMock);
    localStorage.setItem("investment-agent:last-run", runId);
    const user = userEvent.setup();

    render(<AgentRunPanel />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    await user.click(screen.getByRole("button", { name: "取消任务" }));

    expect(await screen.findByText("无法取消研究任务，请稍后重试。")).toBeInTheDocument();
    expect(await screen.findByText("状态：completed", {}, { timeout: 2_000 })).toBeInTheDocument();
    expect(screen.getByText("原任务继续完成")).toBeInTheDocument();
  });

  it("cancels a restored non-terminal run", async () => {
    localStorage.setItem("investment-agent:last-run", "00000000-0000-0000-0000-000000000003");
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(response({ id: "00000000-0000-0000-0000-000000000003", status: "running", executor_mode: "development_only" }))
        .mockResolvedValueOnce(response("event: heartbeat\ndata: {}\n\n", 200, "text/event-stream"))
        .mockResolvedValueOnce(response({ id: "00000000-0000-0000-0000-000000000003", status: "running", executor_mode: "development_only" }))
        .mockResolvedValueOnce(response({ id: "00000000-0000-0000-0000-000000000003", status: "cancelled", executor_mode: "development_only" })),
    );
    const user = userEvent.setup();

    render(<AgentRunPanel />);
    await user.click(await screen.findByRole("button", { name: "取消任务" }));

    expect(await screen.findByText("状态：cancelled")).toBeInTheDocument();
  });
});
