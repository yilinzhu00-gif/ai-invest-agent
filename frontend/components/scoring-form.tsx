"use client";

import { useState, type FormEvent } from "react";

import type { ScoringInput } from "../lib/api/types";

const metricFields = [
  ["pe_ttm", "PE(TTM)", "18.5"],
  ["pb", "市净率 PB", "2.3"],
  ["roe", "ROE(%)", "16.2"],
  ["net_margin", "净利率(%)", "12.5"],
  ["gross_margin", "毛利率(%)", "38"],
  ["rev_growth", "营收增速 YoY(%)", "22"],
  ["profit_growth", "净利润增速 YoY(%)", "28"],
  ["debt_ratio", "资产负债率(%)", "45"],
  ["current_ratio", "流动比率", "1.8"],
  ["ret_60d", "近60日涨跌幅(%)", "8"],
  ["price_vs_ma20", "现价相对MA20(%)", "3.5"],
] as const;

type Props = {
  isLoading: boolean;
  onSubmit: (input: ScoringInput) => void;
};

export function ScoringForm({ isLoading, onSubmit }: Props) {
  const [symbol, setSymbol] = useState("600519");
  const [asOfDate, setAsOfDate] = useState("2026-08-05");
  const [metrics, setMetrics] = useState<Record<string, string>>(
    () => Object.fromEntries(metricFields.map(([key, , value]) => [key, value])),
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = Object.fromEntries(
      Object.entries(metrics)
        .filter(([, value]) => value.trim() !== "")
        .map(([key, value]) => [key, Number(value)]),
    );
    onSubmit({ symbol, as_of_date: asOfDate, metrics: values });
  }

  return (
    <form className="scoring-form" onSubmit={submit}>
      <div className="form-grid form-grid--base">
        <label>
          股票代码
          <input
            aria-label="股票代码"
            inputMode="numeric"
            maxLength={6}
            pattern="[0-9]{6}"
            required
            value={symbol}
            onChange={(event) => setSymbol(event.target.value)}
          />
        </label>
        <label>
          截止日期
          <input
            aria-label="截止日期"
            type="date"
            required
            value={asOfDate}
            onChange={(event) => setAsOfDate(event.target.value)}
          />
        </label>
      </div>

      <fieldset disabled={isLoading}>
        <legend>评分指标（留空的指标不会提交）</legend>
        <div className="form-grid">
          {metricFields.map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                aria-label={label}
                type="number"
                step="any"
                value={metrics[key] ?? ""}
                onChange={(event) => setMetrics((current) => ({ ...current, [key]: event.target.value }))}
              />
            </label>
          ))}
        </div>
      </fieldset>

      <button type="submit" disabled={isLoading}>
        {isLoading ? "评分中…" : "开始评分"}
      </button>
    </form>
  );
}
