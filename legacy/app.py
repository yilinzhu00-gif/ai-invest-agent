"""AI 投研助手 —— Streamlit 主程序。

功能：① 个股行情分析  ② 财报/新闻速读  ③ 研报问答 (RAG)  ④ 结构化评分
运行：streamlit run legacy/app.py
"""
import logging

import streamlit as st

from legacy import agent, finance, llm, rag, scoring

logger = logging.getLogger(__name__)

st.set_page_config(page_title="AI 投研助手", page_icon="📈", layout="wide")
st.title("📈 AI 投研助手")
st.caption("个股分析 · 财报速读 · 研报问答 · 结构化评分 ｜ LLM + RAG Demo")

tab1, tab2, tab3, tab4,tab5 = st.tabs(
    ["📊 个股行情分析", "📰 财报/新闻速读", "📚 研报问答 (RAG)", "🎯 结构化评分","🤖 Agent 投研"]
)

# ---------- 功能 1：个股行情分析 ----------
with tab1:
    st.subheader("输入 A 股代码 → 自动取数 + 技术指标 + AI 解读")
    code = st.text_input("股票代码（6 位）", value="600519",
                         help="例：600519 贵州茅台 / 000001 平安银行")
    if st.button("开始分析", key="analyze"):
        try:
            with st.spinner("获取行情数据中…"):
                df = finance.add_indicators(finance.get_stock_history(code))
            st.line_chart(df.set_index("date")[["close", "MA5", "MA20"]])
            with st.spinner("AI 解读中…"):
                analysis = llm.chat(
                    "以下是某只 A 股的近期行情数据，请用专业但通俗的语言做一段简短解读"
                    "（趋势、量价关系、技术指标信号），并提示风险，不要给出买卖建议：\n\n"
                    + finance.snapshot_text(df, code)
                )
            st.markdown(analysis)
            st.info("⚠️ 以上为 AI 生成的分析，仅供学习参考，不构成任何投资建议。")
        except Exception as error:
            logger.debug("Market analysis failed", exc_info=True)
            st.error(f"出错了：{error}\n\n"
                     "提示：akshare 接口偶尔随版本变化，可 `pip install -U akshare`，"
                     "或确认股票代码正确。")

# ---------- 功能 2：财报/新闻速读 ----------
with tab2:
    st.subheader("粘贴一段财报或新闻 → AI 提炼要点 + 情绪判断")
    text = st.text_area("粘贴文本", height=200, placeholder="把财报段落或新闻正文粘进来…")
    if st.button("速读", key="summarize"):
        if not text.strip():
            st.warning("请先粘贴一段文本。")
        else:
            with st.spinner("AI 分析中…"):
                result = llm.chat(
                    "请阅读下面这段金融文本，输出：\n"
                    "1) 3-5 条关键要点（bullet）\n"
                    "2) 整体情绪倾向（偏正面 / 中性 / 偏负面）及理由\n"
                    "3) 值得关注的风险或不确定性\n\n文本：\n" + text
                )
            st.markdown(result)

# ---------- 功能 3：研报问答 (RAG) ----------
with tab3:
    st.subheader("上传研报 PDF → 针对内容提问（RAG 检索增强）")
    pdf = st.file_uploader("上传 PDF", type=["pdf"])
    if pdf is not None:
        # 同一份 PDF 只索引一次，存进 session_state
        if st.session_state.get("pdf_name") != pdf.name:
            with st.spinner("解析 PDF 并构建向量索引中…"):
                chunks = rag.split_text(rag.load_pdf(pdf))
                st.session_state.store = rag.SimpleVectorStore(chunks)
                st.session_state.pdf_name = pdf.name
                agent.set_research_store(st.session_state.store)
            st.success(f"已索引 {len(st.session_state.store.chunks)} 个文本块，可以提问了。")

        q = st.text_input("针对这份研报提问")
        if st.button("提问", key="rag") and q:
            with st.spinner("检索 + 生成中…"):
                ctx = st.session_state.store.search(q, top_k=3)
                answer = llm.chat(
                    "基于下面从研报中检索到的内容回答问题。"
                    "若内容中没有相关信息，请如实说明，不要编造。\n\n"
                    f"【检索内容】\n{chr(10).join('---' + c for c in ctx)}\n\n【问题】{q}"
                )
            st.markdown(answer)
            with st.expander("查看检索到的原文片段"):
                for i, c in enumerate(ctx, 1):
                    st.text(f"片段 {i}:\n{c}\n")

# ---------- 功能 4：结构化评分 ----------
with tab4:
    st.subheader("输入 A 股代码 → 多维度量化打分 + AI 投资评价")
    s_code = st.text_input("股票代码（6 位）", value="600519", key="score_code",
                           help="例：600519、000001")
    if st.button("开始评分", key="score", type="primary"):
        try:
            with st.spinner("拉取数据并打分中…"):
                metrics = finance.get_metrics(s_code)

            if not metrics:
                st.error("没拿到任何指标，检查股票代码是否正确，或稍后重试。")
            else:
                evaluation = scoring.evaluate_score(metrics)
                if evaluation["status"] == "insufficient_data":
                    st.warning("数据覆盖不足，暂不提供评分或 AI 评价。")
                    st.write(f"覆盖率：{evaluation['coverage']:.0%}")
                    st.write(
                        "缺失核心维度："
                        + "、".join(evaluation["missing_core_dimensions"])
                    )
                    st.write("缺失指标：" + "、".join(evaluation["missing_metrics"]))
                else:
                    result = evaluation["result"]
                    assert result is not None

                    # —— 综合评分 ——
                    c1, c2 = st.columns([1, 2])
                    c1.metric("综合评分", f"{result['total']}",
                              f"{result['grade']} · {result['label']}")
                    c2.progress(result["total"] / 100)

                    # —— 各维度（每项评分依据都展开）——
                    for d in result["dimensions"]:
                        st.write(f"**{d['name']}** — {d['score']} 分"
                                 f"（权重 {d['weight_norm']}，贡献 {d['contribution']}）")
                        st.progress(d["score"] / 100)
                        with st.expander(f"查看「{d['name']}」评分依据"):
                            st.table([{
                                "指标": mm["name"],
                                "原始值": mm["value"],
                                "得分": mm["subscore"],
                                "维度内权重": mm["weight_norm"],
                            } for mm in d["metrics"]])

                    # —— LLM 评价（仅在质量门通过后生成）——
                    with st.spinner("AI 生成投资评价中…"):
                        st.markdown("### 📝 投资评价")
                        st.markdown(scoring.explain_score(
                            result, llm._chat_client, name=s_code, model=llm.CHAT_MODEL
                        ))

                    st.info("⚠️ 以上为基于公开数据的量化打分与 AI 点评，仅供学习参考，"
                            "不构成任何投资建议。")
        except Exception as error:
            logger.debug("Structured scoring failed", exc_info=True)
            st.error(f"出错了：{error}")
# ---------- 功能 5：Agent 投研（LangGraph 编排）----------
with tab5:
    st.subheader("提一个投研问题 → Agent 自主调行情/评分/研报 → 产出报告")
    q = st.text_input("例：帮我分析 600519，结合研报给评级和风险", key="agent_q")
    if st.button("运行 Agent", key="run_agent", type="primary") and q:
        if st.session_state.get("store") is not None:
            agent.set_research_store(st.session_state.store)
        graph = agent.build_agent()
        steps = st.container()
        seen, final = 0, ""
        with st.spinner("Agent 思考与调用工具中…"):
            for ev in graph.stream(
                {"messages": [("user", q)]}, stream_mode="values"
            ):
                for msg in ev["messages"][seen:]:
                    cls = msg.__class__.__name__
                    if getattr(msg, "tool_calls", None):          # Planner 决定调工具
                        for tc in msg.tool_calls:
                            steps.info(f"🔧 调用 `{tc['name']}` → {tc['args']}")
                    elif cls == "ToolMessage":                    # 工具返回
                        with steps.expander(f"📥 `{msg.name}` 返回结果"):
                            st.text(str(msg.content)[:2000])
                    elif cls == "AIMessage" and msg.content:      # 最终报告
                        final = msg.content
                seen = len(ev["messages"])
        st.markdown("### 📝 投研报告")
        st.markdown(final)
        st.info("⚠️ 仅供学习参考，不构成投资建议。")            
