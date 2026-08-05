"use client";

import { useRef, useState } from "react";

import { ScoreResult } from "../../components/score-result";
import { ScoringForm } from "../../components/scoring-form";
import { ApiError, evaluateScore } from "../../lib/api/client";
import type { ScoringInput, ScoringResponse } from "../../lib/api/types";

export default function ScoringPage() {
  const controllerRef = useRef<AbortController | null>(null);
  const lastInputRef = useRef<ScoringInput | null>(null);
  const [response, setResponse] = useState<ScoringResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function requestScore(input: ScoringInput) {
    controllerRef.current?.abort();
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort("timeout"), 15_000);
    controllerRef.current = controller;
    lastInputRef.current = input;
    setIsLoading(true);
    setError(null);
    setResponse(null);

    try {
      setResponse(await evaluateScore(input, controller.signal));
    } catch (caught) {
      if (controller.signal.aborted || (caught instanceof DOMException && caught.name === "AbortError")) {
        setError(
          controller.signal.reason === "timeout"
            ? "请求超时，请稍后重试。"
            : "请求已取消。您可以调整输入后重试。",
        );
      } else if (caught instanceof ApiError) {
        setError(caught.message);
      } else {
        setError("请求未能完成，请稍后重试。");
      }
    } finally {
      window.clearTimeout(timeoutId);
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setIsLoading(false);
      }
    }
  }

  function cancelRequest() {
    controllerRef.current?.abort("cancelled");
  }

  return (
    <main className="page-shell">
      <h1>股票评分</h1>
      <p className="disclaimer">本工具仅用于研究辅助，不构成投资建议或收益承诺。</p>
      <ScoringForm isLoading={isLoading} onSubmit={requestScore} />
      {isLoading && <button type="button" onClick={cancelRequest}>取消请求</button>}
      {error && (
        <section className="error-card" role="alert">
          <p>{error}</p>
          {lastInputRef.current && <button type="button" onClick={() => requestScore(lastInputRef.current!)}>重试</button>}
        </section>
      )}
      {response && <ScoreResult response={response} />}
    </main>
  );
}
