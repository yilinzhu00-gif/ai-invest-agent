"""迁移期 LLM 与 Embedding 调用封装。

chat 和 embedding 可以分别对接不同的服务：
  - chat：DeepSeek / 通义 / 智谱 等（在 .env 里用 OPENAI_API_KEY / OPENAI_BASE_URL 配置）
  - embedding：硅基流动 等支持 embedding 的服务（用 EMBED_API_KEY / EMBED_BASE_URL 配置）

若没单独配置 EMBED_API_KEY，embedding 会自动回退到 chat 那套配置，
所以加这套配置不会影响原本能跑的功能。
"""
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ---- Chat 客户端（例：DeepSeek）----
_chat_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY", ""),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
)

# ---- Embedding 客户端（例：硅基流动）----
# 没配 EMBED_* 时，回退用 chat 的那套，保证不影响原功能。
_embed_client = OpenAI(
    api_key=os.getenv("EMBED_API_KEY") or os.getenv("OPENAI_API_KEY", ""),
    base_url=os.getenv("EMBED_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
)

CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")


def chat(prompt: str,
         system: str = "你是一名专业、严谨的金融投研助手，回答客观中立、不做投资推荐。",
         temperature: float = 0.3) -> str:
    """单轮对话，返回模型回复文本。"""
    resp = _chat_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
    )
    return (resp.choices[0].message.content or "").strip()


def embed(texts: list[str]) -> list[list[float]]:
    """把一批文本转成向量（embedding），用于 RAG 检索。"""
    resp = _embed_client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]
