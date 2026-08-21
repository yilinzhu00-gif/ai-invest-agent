"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { WATCHLIST } from "../lib/research-data";
import { readAgentEvents } from "../lib/sse/agent-events";

type ChatMessage = { id: string; role: "user" | "assistant"; text: string };

export function ResearchChat() {
  const [symbol, setSymbol] = useState("AAPL");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  async function sendMessage() {
    const message = input.trim();
    if (!message || streaming) return;
    setInput("");
    setError(null);
    setMessages((current) => [...current, { id: `${Date.now()}-user`, role: "user", text: message }, { id: `${Date.now()}-assistant`, role: "assistant", text: "" }]);
    const controller = new AbortController();
    abortRef.current = controller;
    setStreaming(true);
    try {
      const response = await fetch("/api/research/chat", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ symbol, message }), signal: controller.signal });
      if (!response.ok) throw new Error("stream_unavailable");
      for await (const event of readAgentEvents(response)) {
        if (event.event !== "delta" || typeof event.data.text !== "string") continue;
        setMessages((current) => current.map((item, index) => index === current.length - 1 ? { ...item, text: item.text + event.data.text } : item));
      }
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) setError("流式连接暂时不可用，请稍后重试。");
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  return (
    <main className="product-shell chat-shell">
      <div className="chat-heading"><div><p className="product-kicker">RESEARCH CHAT</p><h1>研究对话</h1><p>像和一位 buy-side 分析师对话一样，逐步拆解你的问题。</p></div><Link className="quiet-link" href="/reports">查看报告 ↗</Link></div>
      <section className="chat-layout">
        <aside className="chat-context"><p className="section-label">研究标的</p><div className="ticker-picker">{WATCHLIST.map((stock) => <button key={stock.symbol} type="button" className={stock.symbol === symbol ? "ticker-option ticker-option--active" : "ticker-option"} onClick={() => setSymbol(stock.symbol)}><span>{stock.symbol}</span><small>{stock.price}</small></button>)}</div><div className="context-note"><span className="status-dot" /> SSE 流式连接<br /><small>回答会逐字返回，可随时停止。</small></div></aside>
        <section className="chat-panel" aria-label="Research Chat">
          <div className="chat-messages">
            {messages.length === 0 && <div className="chat-empty"><div className="chat-empty-icon">✦</div><h2>今天想研究什么？</h2><p>试试：<button type="button" onClick={() => setInput("AAPL 的核心投资逻辑和最大风险是什么？")}>“AAPL 的核心投资逻辑和最大风险是什么？”</button></p></div>}
            {messages.map((message) => <article className={`chat-message chat-message--${message.role}`} key={message.id}><span className="message-avatar">{message.role === "user" ? "你" : "R"}</span><div><p className="message-role">{message.role === "user" ? "你" : "Research Copilot"}</p><p className="message-text">{message.text || (streaming ? "正在检索和组织证据…" : "")}{message.role === "assistant" && streaming && message.id === messages.at(-1)?.id && <span className="typing-cursor" />}</p></div></article>)}
          </div>
          {error && <p className="chat-error" role="alert">{error}</p>}
          <div className="chat-composer"><textarea aria-label="研究问题" placeholder={`询问 ${symbol} 的财务、估值或风险…`} value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendMessage(); } }} rows={2} /><button className="send-button" type="button" onClick={() => void sendMessage()} disabled={!input.trim() || streaming}>{streaming ? "生成中…" : "发送 ↗"}</button></div><p className="composer-hint">Enter 发送 · Shift + Enter 换行 · 仅供研究参考</p>
        </section>
      </section>
    </main>
  );
}
