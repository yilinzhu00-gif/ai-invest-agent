import { z } from "zod";

import { scoringResponseSchema, type ScoringInput, type ScoringResponse } from "./types";

const errorEnvelopeSchema = z.object({
  error: z.object({ code: z.string() }),
  correlation_id: z.string().optional(),
});

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly code?: string,
    public readonly correlationId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function safeMessage(status: number): string {
  if (status >= 500) return "服务暂时不可用，请稍后重试。";
  if (status >= 400) return "请求未能完成。请检查输入后重试。";
  return "请求未能完成，请稍后重试。";
}

export async function evaluateScore(
  input: ScoringInput,
  signal?: AbortSignal,
): Promise<ScoringResponse> {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  let response: Response;

  try {
    response = await fetch(`${baseUrl}/api/v1/scoring/evaluate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(input),
      signal,
    });
  } catch (error) {
    if (signal?.aborted || (error instanceof DOMException && error.name === "AbortError")) {
      throw new DOMException("The request was aborted.", "AbortError");
    }
    throw new ApiError("网络连接失败，请检查后重试。");
  }

  if (!response.ok) {
    const parsed = errorEnvelopeSchema.safeParse(await response.json().catch(() => null));
    const headerCorrelationId = response.headers.get("x-correlation-id") ?? undefined;
    throw new ApiError(
      safeMessage(response.status),
      response.status,
      parsed.success ? parsed.data.error.code : undefined,
      parsed.success ? parsed.data.correlation_id ?? headerCorrelationId : headerCorrelationId,
    );
  }

  const parsed = scoringResponseSchema.safeParse(await response.json().catch(() => null));
  if (!parsed.success) {
    throw new ApiError("响应格式不符合预期，请稍后重试。", response.status);
  }
  return parsed.data;
}
