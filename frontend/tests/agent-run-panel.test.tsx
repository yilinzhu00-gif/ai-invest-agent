import { render, screen } from "@testing-library/react";
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
    await user.type(screen.getByLabelText("研究问题"), "上证指数走势");
    await user.click(screen.getByRole("button", { name: "启动研究" }));

    expect(await screen.findByText("研究已完成")).toBeInTheDocument();
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
