"use client";

import { useEffect, useState } from "react";

import { useAuth } from "./auth-provider";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function splitItems(value: string): string[] {
  return value.split(/[，,]/).map((item) => item.trim()).filter(Boolean);
}

export function MemoryProfileForm() {
  const auth = useAuth();
  const [industries, setIndustries] = useState("");
  const [style, setStyle] = useState("");
  const [riskLevel, setRiskLevel] = useState("unknown");
  const [stocks, setStocks] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!auth.requestHeaders) return;
    void fetch(`${apiBaseUrl}/api/v1/memory/user`, { headers: auth.requestHeaders })
      .then((response) => response.ok ? response.json() as Promise<Record<string, unknown> | null> : null)
      .then((profile) => {
        if (!profile) return;
        setIndustries(Array.isArray(profile.industries) ? profile.industries.join(", ") : "");
        setStyle(typeof profile.investment_style === "string" ? profile.investment_style : "");
        setRiskLevel(typeof profile.risk_level === "string" ? profile.risk_level : "unknown");
        setStocks(Array.isArray(profile.historical_stocks) ? profile.historical_stocks.join(", ") : "");
      })
      .catch(() => undefined);
  }, [auth.requestHeaders]);

  async function save() {
    if (!auth.requestHeaders) return;
    const response = await fetch(`${apiBaseUrl}/api/v1/memory/user`, {
      method: "POST",
      headers: { ...auth.requestHeaders, "content-type": "application/json" },
      body: JSON.stringify({
        industries: splitItems(industries),
        investment_preferences: splitItems(style),
        investment_style: style.trim() || null,
        risk_level: riskLevel,
        historical_stocks: splitItems(stocks).map((item) => item.toUpperCase()),
      }),
    });
    setMessage(response.ok ? "Memory 已保存，后续 Planner 会使用这些偏好。" : "Memory 保存失败，请稍后重试。");
  }

  return (
    <section className="memory-profile-form" aria-label="长期研究偏好">
      <div><h2>长期研究偏好</h2><p>这些信息只作为研究上下文，不会替代数据引用。</p></div>
      <label>关注行业<input value={industries} onChange={(event) => setIndustries(event.target.value)} placeholder="例如：AI, 半导体" /></label>
      <label>投资风格<input value={style} onChange={(event) => setStyle(event.target.value)} placeholder="例如：成长、关注现金流" /></label>
      <label>风险偏好<select value={riskLevel} onChange={(event) => setRiskLevel(event.target.value)}><option value="unknown">未设置</option><option value="conservative">稳健</option><option value="balanced">平衡</option><option value="aggressive">进取</option></select></label>
      <label>历史关注股票<input value={stocks} onChange={(event) => setStocks(event.target.value)} placeholder="例如：NVDA, AAPL" /></label>
      <button type="button" onClick={() => void save()} disabled={!auth.requestHeaders}>保存偏好</button>
      {message && <p className="success-note" role="status">{message}</p>}
    </section>
  );
}
