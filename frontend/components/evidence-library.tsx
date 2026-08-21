"use client";

import { useState } from "react";

import { useAuth } from "./auth-provider";

type UploadedDocument = {
  id: string;
  filename: string;
  symbol: string | null;
  document_type: "financial_report" | "announcement" | "research_report" | "broker_report" | "industry_report" | "policy" | "other";
  source_url: string | null;
  version: number;
  status: string;
  page_count: number;
  parsed_block_count: number;
};

type EvidenceResult = {
  evidence_id: string;
  document_id: string;
  document_version: number;
  filename: string;
  source_url: string | null;
  page_number: number;
  block_id: string;
  text: string;
  parser: string;
  confidence: number;
};

type TransactionFactEvidence = {
  page_number: number;
  block_id: string;
  text: string;
};

type TransactionFactRow = {
  field: string;
  value: string;
  evidence: TransactionFactEvidence[];
};

type TransactionFacts = {
  document_id: string;
  filename: string;
  document_version: number;
  rows: TransactionFactRow[];
  boundary: string;
};

type MarketReaction = {
  symbol: string;
  announcement_date: string;
  event_date: string;
  event_window: [number, number];
  benchmark_indices: { name: string; symbol: string; source: string }[];
  formula: string;
  before_after_change: {
    before_date: string;
    event_date: string;
    after_date: string;
    before_to_event_return_percent: number;
    event_to_after_return_percent: number;
  };
  window_result: {
    start_offset: number;
    end_offset: number;
    start_date: string;
    end_date: string;
    stock_start_close: number;
    stock_end_close: number;
    csi_300_start_close: number;
    csi_300_end_close: number;
    industry_start_close: number;
    industry_end_close: number;
    stock_return_percent: number;
    csi_300_return_percent: number;
    industry_return_percent: number;
    excess_vs_csi_300_percentage_points: number;
    excess_vs_industry_percentage_points: number;
  };
  volume_volatility_change: {
    pre_period: string;
    post_period: string;
    pre_average_volume: number | null;
    post_average_volume: number | null;
    volume_change_percent: number | null;
    pre_daily_volatility_percent: number | null;
    post_daily_volatility_percent: number | null;
    volatility_change_percentage_points: number | null;
  };
  market_dates: {
    event_offset: number;
    market_date: string;
    stock_close: number;
    stock_volume: number | null;
    csi_300_close: number;
    industry_index_close: number;
  }[];
  missing_trading_dates: string[];
  missing_trading_dates_definition: string;
  source: string;
  boundary: string;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function uploadUrl(input: {
  filename: string;
  symbol: string;
  documentType: string;
  sourceUrl: string;
}): string {
  const params = new URLSearchParams({ filename: input.filename, document_type: input.documentType });
  if (input.symbol) params.set("symbol", input.symbol);
  if (input.sourceUrl) params.set("source_url", input.sourceUrl);
  return `${apiBaseUrl}/api/v1/documents?${params.toString()}`;
}

export function EvidenceLibrary() {
  const auth = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [symbol, setSymbol] = useState("");
  const [documentType, setDocumentType] = useState<UploadedDocument["document_type"]>("announcement");
  const [sourceUrl, setSourceUrl] = useState("");
  const [uploaded, setUploaded] = useState<UploadedDocument | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<EvidenceResult[]>([]);
  const [transactionFacts, setTransactionFacts] = useState<TransactionFacts | null>(null);
  const [announcementDate, setAnnouncementDate] = useState("");
  const [industryIndexSymbol, setIndustryIndexSymbol] = useState("");
  const [industryIndexName, setIndustryIndexName] = useState("");
  const [marketReaction, setMarketReaction] = useState<MarketReaction | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function upload() {
    if (!file || !auth.requestHeaders) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(uploadUrl({
        filename: file.name,
        symbol,
        documentType,
        sourceUrl: sourceUrl.trim(),
      }), {
        method: "POST",
        headers: { ...auth.requestHeaders, "content-type": "application/octet-stream" },
        body: file,
      });
      if (!response.ok) throw new Error("upload_failed");
      const document = await response.json() as UploadedDocument;
      setUploaded(document);
      setResults([]);
      setQuery("");
      setTransactionFacts(null);
      setMarketReaction(null);
    } catch {
      setError("上传或解析失败。请确认文件格式、大小和来源链接后重试。");
    } finally {
      setBusy(false);
    }
  }

  async function calculateMarketReaction() {
    if (!uploaded || uploaded.document_type !== "announcement" || !auth.requestHeaders) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/documents/${uploaded.id}/market-reaction`, {
        method: "POST",
        headers: { ...auth.requestHeaders, "content-type": "application/json" },
        body: JSON.stringify({
          announcement_date: announcementDate,
          industry_index_symbol: industryIndexSymbol,
          industry_index_name: industryIndexName.trim(),
          event_window: 20,
        }),
      });
      if (!response.ok) throw new Error("market_reaction_failed");
      setMarketReaction(await response.json() as MarketReaction);
    } catch {
      setError("无法取得完整事件窗口行情。请核对公告日、行业指数代码，或稍后重试。");
    } finally {
      setBusy(false);
    }
  }

  async function extractTransactionFacts() {
    if (!uploaded || uploaded.document_type !== "announcement" || !auth.requestHeaders) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/documents/${uploaded.id}/transaction-facts`,
        { method: "POST", headers: auth.requestHeaders },
      );
      if (!response.ok) throw new Error("transaction_facts_failed");
      setTransactionFacts(await response.json() as TransactionFacts);
    } catch {
      setError("无法生成交易事实表。请确认该公告已解析为可引用文本后重试。");
    } finally {
      setBusy(false);
    }
  }

  async function search() {
    if (!query.trim() || !auth.requestHeaders) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/knowledge/search`, {
        method: "POST",
        headers: { ...auth.requestHeaders, "content-type": "application/json" },
        body: JSON.stringify({ query: query.trim(), document_id: uploaded?.id, limit: 10 }),
      });
      if (!response.ok) throw new Error("search_failed");
      const payload = await response.json() as { results: EvidenceResult[] };
      setResults(payload.results);
    } catch {
      setError("检索失败，请稍后重试。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="evidence-library" aria-label="公告与研报证据库">
      <h2>公告与研报证据库</h2>
      <p>首版支持 PDF、MD、HTML、CSV；只保存解析出的可引用文本块，来源链接仅作登记，不会由系统主动下载。</p>
      <div className="form-grid form-grid--base">
        <label>
          股票代码 / 标的（可选）
          <input aria-label="股票代码" maxLength={6} placeholder="例如 600519 或 NVDA" value={symbol}
            onChange={(event) => setSymbol(event.target.value.replace(/[^a-zA-Z0-9.-]/g, "").toUpperCase())} />
        </label>
        <label>
          文档类型
          <select value={documentType} onChange={(event) => setDocumentType(event.target.value as UploadedDocument["document_type"])}>
            <option value="announcement">公司公告</option>
            <option value="financial_report">财报 / 年报</option>
            <option value="broker_report">券商研报</option>
            <option value="industry_report">行业报告</option>
            <option value="policy">政策文件</option>
            <option value="other">其他材料</option>
          </select>
        </label>
        <label>
          来源链接（可选）
          <input type="url" placeholder="https://..." value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} />
        </label>
        <label>
          公告或研报文件
          <input type="file" accept=".pdf,.md,.html,.csv" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        </label>
      </div>
      <button type="button" onClick={() => void upload()} disabled={!file || auth.status !== "authenticated" || busy}>
        上传并解析
      </button>
      {error && <p className="error-card" role="alert">{error}</p>}
      {uploaded && (
        <section className="document-summary" aria-label="解析结果">
          <h3>已建立证据版本</h3>
          <p>{uploaded.filename} · v{uploaded.version} · {uploaded.page_count} 页 · {uploaded.parsed_block_count} 个文本块</p>
          {uploaded.status === "ready" ? (
            <p className="success-note">可按“文件 + 版本 + 页码 + 文本块”定位引用。</p>
          ) : (
            <p className="missing-evidence" role="alert">未提取到可信文字层：该文件标为“需 OCR”，不会生成或检索伪造引用。</p>
          )}
        </section>
      )}
      {uploaded?.status === "ready" && uploaded.document_type === "announcement" && (
        <section className="transaction-fact-action" aria-label="结构化提取重大事项">
          <h3>结构化提取重大事项</h3>
          <p>生成固定字段的交易事实表。表中只展示公告原文和页码；没有直接披露的字段将显示“公告未披露”。</p>
          <button type="button" onClick={() => void extractTransactionFacts()} disabled={auth.status !== "authenticated" || busy}>
            生成交易事实表
          </button>
        </section>
      )}
      {transactionFacts && (
        <section className="transaction-facts" aria-label="交易事实表">
          <h3>交易事实表</h3>
          <p>{transactionFacts.filename} · v{transactionFacts.document_version}。逐项可按页码回到原公告核对。</p>
          <div className="transaction-facts-scroll">
            <table aria-label="交易事实表">
              <thead>
                <tr><th scope="col">字段</th><th scope="col">公告原文</th><th scope="col">页码</th></tr>
              </thead>
              <tbody>
                {transactionFacts.rows.map((row) => (
                  <tr key={row.field}>
                    <th scope="row">{row.field}</th>
                    <td>
                      {row.evidence.length === 0 ? row.value : (
                        <ul className="transaction-fact-excerpts">
                          {row.evidence.map((item) => <li key={`${item.page_number}-${item.block_id}`}>{item.text}</li>)}
                        </ul>
                      )}
                    </td>
                    <td>{row.evidence.length === 0 ? "—" : row.evidence.map((item) => `第 ${item.page_number} 页`).join("；")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="disclaimer">{transactionFacts.boundary}</p>
        </section>
      )}
      {uploaded?.status === "ready" && uploaded.document_type === "announcement" && (
        <section id="market-reaction" className="market-reaction-action" aria-label="计算市场反应">
          <h3>计算市场反应</h3>
          <p>以公告日为锚点计算 [-20, +20] 个共同交易日窗口。行业指数由研究员指定，系统不会根据股票代码推测行业归属。</p>
          <div className="form-grid form-grid--base">
            <label>
              公告日期
              <input type="date" value={announcementDate} onChange={(event) => setAnnouncementDate(event.target.value)} />
            </label>
            <label>
              行业指数代码
              <input inputMode="numeric" maxLength={6} placeholder="例如 801010" value={industryIndexSymbol}
                onChange={(event) => setIndustryIndexSymbol(event.target.value.replace(/\D/g, ""))} />
            </label>
            <label>
              行业指数名称
              <input placeholder="例如：申万一级行业指数" value={industryIndexName} onChange={(event) => setIndustryIndexName(event.target.value)} />
            </label>
          </div>
          <button type="button" onClick={() => void calculateMarketReaction()} disabled={
            auth.status !== "authenticated" || busy || !announcementDate || !/^\d{6}$/.test(industryIndexSymbol) || !industryIndexName.trim()
          }>
            计算 [-20, +20] 市场反应
          </button>
        </section>
      )}
      {marketReaction && (
        <section className="market-reaction" aria-label="市场反应结果">
          <h3>市场反应结果</h3>
          <p>{marketReaction.symbol} · 公告日期 {marketReaction.announcement_date} · 对齐后的事件交易日 {marketReaction.event_date} · 窗口 [{marketReaction.event_window[0]}, +{marketReaction.event_window[1]}]</p>
          <p>基准指数：{marketReaction.benchmark_indices.map((item) => `${item.name}（${item.symbol}）`).join("；")}</p>
          <p className="disclaimer">{marketReaction.formula}</p>
          <div className="market-reaction-scroll">
            <table aria-label="事件窗口收益率">
              <thead><tr><th>指标</th><th>期初</th><th>期末</th><th>结果</th></tr></thead>
              <tbody>
                <tr><th>个股区间收益率</th><td>{marketReaction.window_result.start_date} / {marketReaction.window_result.stock_start_close}</td><td>{marketReaction.window_result.end_date} / {marketReaction.window_result.stock_end_close}</td><td>{marketReaction.window_result.stock_return_percent}%</td></tr>
                <tr><th>沪深300区间收益率</th><td>{marketReaction.window_result.start_date} / {marketReaction.window_result.csi_300_start_close}</td><td>{marketReaction.window_result.end_date} / {marketReaction.window_result.csi_300_end_close}</td><td>{marketReaction.window_result.csi_300_return_percent}%</td></tr>
                <tr><th>行业指数区间收益率</th><td>{marketReaction.window_result.start_date} / {marketReaction.window_result.industry_start_close}</td><td>{marketReaction.window_result.end_date} / {marketReaction.window_result.industry_end_close}</td><td>{marketReaction.window_result.industry_return_percent}%</td></tr>
                <tr><th>相对沪深300超额收益</th><td colSpan={2}>个股区间收益率 − 沪深300区间收益率</td><td>{marketReaction.window_result.excess_vs_csi_300_percentage_points} 个百分点</td></tr>
                <tr><th>相对行业指数超额收益</th><td colSpan={2}>个股区间收益率 − 行业指数区间收益率</td><td>{marketReaction.window_result.excess_vs_industry_percentage_points} 个百分点</td></tr>
              </tbody>
            </table>
          </div>
          <dl className="market-reaction-metrics">
            <div><dt>{marketReaction.before_after_change.before_date} → {marketReaction.before_after_change.event_date}</dt><dd>{marketReaction.before_after_change.before_to_event_return_percent}%</dd></div>
            <div><dt>{marketReaction.before_after_change.event_date} → {marketReaction.before_after_change.after_date}</dt><dd>{marketReaction.before_after_change.event_to_after_return_percent}%</dd></div>
            <div><dt>平均成交量 {marketReaction.volume_volatility_change.pre_period} / {marketReaction.volume_volatility_change.post_period}</dt><dd>{marketReaction.volume_volatility_change.pre_average_volume ?? "未提供"} / {marketReaction.volume_volatility_change.post_average_volume ?? "未提供"}</dd></div>
            <div><dt>成交量变化</dt><dd>{marketReaction.volume_volatility_change.volume_change_percent ?? "未提供"}{marketReaction.volume_volatility_change.volume_change_percent === null ? "" : "%"}</dd></div>
            <div><dt>日收益率波动率（前 / 后）</dt><dd>{marketReaction.volume_volatility_change.pre_daily_volatility_percent === null ? "未提供" : `${marketReaction.volume_volatility_change.pre_daily_volatility_percent}%`} / {marketReaction.volume_volatility_change.post_daily_volatility_percent === null ? "未提供" : `${marketReaction.volume_volatility_change.post_daily_volatility_percent}%`}</dd></div>
            <div><dt>波动率变化</dt><dd>{marketReaction.volume_volatility_change.volatility_change_percentage_points ?? "未提供"}{marketReaction.volume_volatility_change.volatility_change_percentage_points === null ? "" : " 个百分点"}</dd></div>
          </dl>
          <h4>事件窗口行情日期</h4>
          <div className="market-reaction-scroll">
            <table aria-label="事件窗口行情日期">
              <thead><tr><th>事件日</th><th>行情日期</th><th>个股收盘价</th><th>成交量</th><th>沪深300收盘价</th><th>行业指数收盘价</th></tr></thead>
              <tbody>{marketReaction.market_dates.map((item) => <tr key={item.market_date}><td>{item.event_offset >= 0 ? `+${item.event_offset}` : item.event_offset}</td><td>{item.market_date}</td><td>{item.stock_close}</td><td>{item.stock_volume ?? "未提供"}</td><td>{item.csi_300_close}</td><td>{item.industry_index_close}</td></tr>)}</tbody>
            </table>
          </div>
          <h4>缺失交易日</h4>
          <p>{marketReaction.missing_trading_dates_definition}</p>
          <p>{marketReaction.missing_trading_dates.length ? marketReaction.missing_trading_dates.join("、") : "无"}</p>
          <p className="result-source">行情来源：{marketReaction.source}</p>
          <p className="disclaimer">{marketReaction.boundary}</p>
        </section>
      )}
      <div className="evidence-search">
        <label>
          在已上传材料中检索
          <input value={query} placeholder="例如：交易对价、发行股份、业绩承诺" onChange={(event) => setQuery(event.target.value)} />
        </label>
        <button type="button" onClick={() => void search()} disabled={!query.trim() || auth.status !== "authenticated" || busy}>检索证据</button>
      </div>
      {results.length > 0 && (
        <ol className="evidence-results" aria-label="检索证据">
          {results.map((item) => (
            <li key={item.evidence_id}>
              <p className="citation-label">{item.filename} · v{item.document_version} · 第 {item.page_number} 页 · 块 {item.block_id}</p>
              <p>{item.text}</p>
              <p className="citation-meta">解析方式：{item.parser}；置信度：{Math.round(item.confidence * 100)}%</p>
              {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">查看登记的来源链接</a>}
            </li>
          ))}
        </ol>
      )}
      {uploaded?.status === "ready" && results.length === 0 && query && !busy && <p className="empty-state">未找到匹配文本；这不代表该事实不存在，请换关键词或人工阅读原文件。</p>}
    </section>
  );
}
