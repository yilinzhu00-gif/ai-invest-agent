import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ScoringPage from "../app/scoring/page";
import { evaluateScore } from "../lib/api/client";
import type { ScoringResponse } from "../lib/api/types";

const fullResponse: ScoringResponse = {
  status: "ok",
  coverage: 1,
  missing_core_dimensions: [],
  missing_metrics: [],
  result: {
    total: 82.3,
    grade: "B",
    label: "看好",
    dimensions: [
      {
        name: "估值",
        score: 79,
        weight: 0.2,
        weight_norm: 0.2,
        contribution: 15.8,
        metrics: [{ name: "PE(TTM)", value: 18.5, subscore: 82, weight: 0.6, weight_norm: 0.6 }],
      },
    ],
  },
};

const insufficientResponse: ScoringResponse = {
  status: "insufficient_data",
  coverage: 0.2,
  missing_core_dimensions: ["盈利能力", "成长性", "财务健康"],
  missing_metrics: ["pb", "roe"],
  result: null,
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "x-correlation-id": "request-123" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("scoring page", () => {
  it("shows only coverage and missing items for insufficient data", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(insufficientResponse));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<ScoringPage />);
    await user.clear(screen.getByLabelText("市净率 PB"));
    await user.click(screen.getByRole("button", { name: "开始评分" }));

    expect(await screen.findByText("数据不足，暂不提供评分")).toBeInTheDocument();
    expect(screen.getByText("覆盖率：20%")).toBeInTheDocument();
    expect(screen.getByText("缺失核心维度：盈利能力、成长性、财务健康")).toBeInTheDocument();
    expect(screen.getByText("缺失指标：pb、roe")).toBeInTheDocument();
    expect(screen.queryByText("总分")).not.toBeInTheDocument();
    expect(screen.queryByText("评级")).not.toBeInTheDocument();
    expect(screen.queryByText("看好")).not.toBeInTheDocument();
    const submitted = JSON.parse(fetchMock.mock.calls[0][1].body) as { metrics: Record<string, number> };
    expect(submitted.metrics).not.toHaveProperty("pb");
  });

  it("shows total, grade, label, and dimension detail for a complete response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(fullResponse)));
    const user = userEvent.setup();

    render(<ScoringPage />);
    await user.click(screen.getByRole("button", { name: "开始评分" }));

    expect(await screen.findByText("82.3")).toBeInTheDocument();
    expect(screen.getByText("评级：B" )).toBeInTheDocument();
    expect(screen.getByText("结论：看好")).toBeInTheDocument();
    expect(screen.getByText("估值：79")).toBeInTheDocument();
    expect(screen.getByText("PE(TTM)：18.5，子分 82")).toBeInTheDocument();
  });

  it("shows a safe API error and Retry recovers on the next response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(jsonResponse({ error: { code: "validation_error" }, correlation_id: "bad-1" }, 422))
        .mockResolvedValueOnce(jsonResponse(fullResponse)),
    );
    const user = userEvent.setup();

    render(<ScoringPage />);
    await user.click(screen.getByRole("button", { name: "开始评分" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("请求未能完成。请检查输入后重试。");

    await user.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText("82.3")).toBeInTheDocument();
  });

  it("disables submit while loading and Cancel aborts the in-flight request", async () => {
    let abortSignal: AbortSignal | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_: string, init: RequestInit) => {
        abortSignal = init.signal as AbortSignal;
        return new Promise((_, reject) => {
          abortSignal?.addEventListener("abort", () => reject(abortSignal?.reason));
        });
      }),
    );
    const user = userEvent.setup();

    render(<ScoringPage />);
    await user.click(screen.getByRole("button", { name: "开始评分" }));
    expect(screen.getByRole("button", { name: "评分中…" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "取消请求" }));
    await waitFor(() => expect(abortSignal?.aborted).toBe(true));
    expect(await screen.findByRole("alert")).toHaveTextContent("请求已取消");
  });
});

describe("scoring API client", () => {
  const input = {
    symbol: "600519",
    as_of_date: "2026-08-05",
    metrics: { pe_ttm: 18.5 },
  };

  it("sends the specified JSON contract and rejects malformed success responses", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(insufficientResponse));
    vi.stubGlobal("fetch", fetchMock);

    await expect(evaluateScore(input)).resolves.toEqual(insufficientResponse);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/scoring/evaluate",
      expect.objectContaining({
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(input),
      }),
    );

    fetchMock.mockResolvedValueOnce(jsonResponse({ status: "ok", coverage: 1, result: null }));
    await expect(evaluateScore(input)).rejects.toThrow("响应格式不符合预期");
  });

  it("exposes only a safe typed API error for non-success responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ error: { code: "internal_server_error" }, correlation_id: "safe-500" }, 500)),
    );

    await expect(evaluateScore(input)).rejects.toMatchObject({
      message: "服务暂时不可用，请稍后重试。",
      status: 500,
      code: "internal_server_error",
      correlationId: "safe-500",
    });
  });

  it("preserves a correlation ID from response headers when an error body is malformed", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ unexpected: true }, 500)));

    await expect(evaluateScore(input)).rejects.toMatchObject({
      message: "服务暂时不可用，请稍后重试。",
      status: 500,
      correlationId: "request-123",
    });
  });
});
