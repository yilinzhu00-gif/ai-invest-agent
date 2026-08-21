import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../components/auth-provider", () => ({
  useAuth: () => ({
    status: "authenticated",
    mode: "development",
    requestHeaders: {
      "X-Development-Principal-ID": "local-user",
      "X-Development-Workspace-ID": "local-workspace",
    },
    error: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
  }),
}));

import { ResearchCreateForm } from "../components/research-create-form";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("ResearchCreateForm", () => {
  it("submits a professional research task configuration", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ id: "run-1" }),
      { status: 202, headers: { "content-type": "application/json" } },
    ));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<ResearchCreateForm />);
    await user.selectOptions(screen.getByLabelText("研究标的"), "AAPL");
    await user.selectOptions(screen.getByLabelText("研究类型"), "risk");
    await user.selectOptions(screen.getByLabelText("时间范围"), "custom");
    fireEvent.change(screen.getByLabelText("开始日期"), { target: { value: "2024-01-01" } });
    fireEvent.change(screen.getByLabelText("结束日期"), { target: { value: "2026-01-01" } });
    await user.selectOptions(screen.getByLabelText("研究深度"), "deep_research");
    await user.selectOptions(screen.getByLabelText("输出格式"), "pdf");
    await user.click(screen.getByRole("button", { name: "创建研究任务" }));

    expect(await screen.findByText("任务已创建：run-1")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/research/tasks"),
      expect.objectContaining({
        body: expect.stringContaining('"target":"AAPL"'),
      }),
    );
    expect(fetchMock.mock.calls[0]?.[1]?.body).toContain('"time_range":"custom"');
    expect(fetchMock.mock.calls[0]?.[1]?.body).toContain('"output_format":"pdf"');
  });
});
