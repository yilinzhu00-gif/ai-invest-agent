"""LangGraph Agent 编排层。

把项目现有的能力（finance 取数 / scoring 评分 / rag 检索）包装成 Tool，
由 LLM 自主规划调用顺序，跑一个 ReAct-on-graph 循环，最后产出投研报告。

设计要点：
- 复用 llm.py 的同一套 env（OPENAI_API_KEY / OPENAI_BASE_URL / CHAT_MODEL），
  用 LangChain 的 ChatOpenAI 接同一个 OpenAI 兼容服务（DeepSeek 等都支持 tool calling）。
- 三个工具：行情快照 / 结构化评分 / 研报检索。手写 RAG 不动，只包一层。
- 流程：planner(LLM) 决定调哪个工具 → ToolNode 执行 → 回到 planner → 信息够了停下出报告。

单测：  python agent.py
"""
import logging
import os
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from legacy import finance, scoring

logger = logging.getLogger(__name__)

load_dotenv()  # 和 llm.py 用同一套 .env


# ============================================================
# 0. RAG 研报库的“当前 store”——由 app.py 索引完 PDF 后注入
#    （工具在运行期读取它；没上传研报时优雅降级）
# ============================================================
_CURRENT_STORE = None


def set_research_store(store) -> None:
    """app.py 索引完 PDF 后调用，把 rag.SimpleVectorStore 交给 Agent 用。"""
    global _CURRENT_STORE
    _CURRENT_STORE = store


# ============================================================
# 1. 工具：包装你已有的能力（docstring 是给 LLM 看的，决定它何时调用）
# ============================================================
@tool
def get_market_snapshot(code: str) -> str:
    """获取 A 股个股近 120 日行情快照：最新价、区间涨跌幅、MA5/MA20/RSI14、量价情况。
    参数 code 为 6 位股票代码，例如 '600519'。"""
    try:
        df = finance.add_indicators(finance.get_stock_history(code))
        return finance.snapshot_text(df, code)
    except Exception as error:
        logger.debug("Market snapshot tool failed", exc_info=True)
        return f"（行情取数失败，可稍后重试：{error}）"


@tool
def score_stock(code: str) -> dict:
    """对 A 股个股做多维度量化打分（估值/盈利能力/成长性/财务健康/动量），
    数据充分时返回综合分与评级，数据不足时只返回覆盖诊断。参数 code 为 6 位股票代码。"""
    try:
        metrics = finance.get_metrics(code)
        if not metrics:
            return {"error": f"未取到 {code} 的任何指标，请确认代码是否正确或稍后重试。"}
        return scoring.evaluate_score(metrics)
    except Exception as error:
        logger.debug("Scoring tool failed", exc_info=True)
        return {"error": f"评分失败，可稍后重试：{error}"}


@tool
def search_research(query: str) -> str:
    """在用户已上传的研报库中检索与 query 最相关的片段（手写 RAG，余弦相似度）。
    若用户尚未上传研报 PDF，会返回提示，此时不要再调用本工具。"""
    if _CURRENT_STORE is None:
        return "（研报库为空：用户尚未上传研报 PDF，本工具暂不可用。）"
    hits = _CURRENT_STORE.search(query, top_k=3)
    return "\n\n---\n".join(hits)


TOOLS = [get_market_snapshot, score_stock, search_research]


# ============================================================
# 2. LLM：复用 llm.py 的同一套 env 配置
# ============================================================
def _build_llm():
    return ChatOpenAI(
        model=os.getenv("CHAT_MODEL", "gpt-4o-mini"),
        api_key=os.getenv("OPENAI_API_KEY", ""),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        temperature=0.3,
    ).bind_tools(TOOLS)


PLANNER_PROMPT = """你是一个 A 股投研 Agent 的规划器，目标是产出一份结构化的个股投研简报。
你可以按需自主决定调用顺序与次数，使用以下工具：
- get_market_snapshot(code)：取行情与技术面
- score_stock(code)：取多维度量化评分
- search_research(query)：检索用户上传的研报（若有）

建议流程：先取行情，再做量化评分；若研报库可用，针对关键问题检索佐证。
当信息齐全后停止调用工具，直接输出报告，包含：
1) 一句话结论与评级
2) 行情/技术面要点
3) 量化评分解读（引用各维度分数与贡献）
4) 研报佐证（若检索到，否则略过）
5) 主要风险
只依据工具返回的数据，不要编造未给出的指标。结尾固定加一行：
「本内容仅供学习参考，不构成任何投资建议。」"""


# ============================================================
# 3. LangGraph：ReAct 循环
# ============================================================
class State(TypedDict):
    messages: Annotated[list, add_messages]


def build_agent():
    """编译并返回一个可执行的 LangGraph agent。"""
    llm = _build_llm()

    def planner(state: State):
        msgs = [SystemMessage(content=PLANNER_PROMPT)] + state["messages"]
        return {"messages": [llm.invoke(msgs)]}

    def route(state: State):
        # 最后一条 AI 消息里还有 tool_calls → 继续执行工具；否则结束（此时内容即报告）
        return "tools" if state["messages"][-1].tool_calls else END

    g = StateGraph(State)
    g.add_node("planner", planner)
    g.add_node("tools", ToolNode(TOOLS))
    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", route, {"tools": "tools", END: END})
    g.add_edge("tools", "planner")   # 工具执行完回到规划器 → 形成循环
    return g.compile()


def run(question: str) -> str:
    """便捷入口：一次性问答，返回最终报告文本。"""
    app = build_agent()
    out = app.invoke({"messages": [HumanMessage(content=question)]})
    return out["messages"][-1].content


if __name__ == "__main__":
    print(run("帮我分析一下 600519 贵州茅台，给评级和主要风险"))
