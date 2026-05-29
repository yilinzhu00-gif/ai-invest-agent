"""极简 RAG 实现：PDF 文本提取 → 切分 → 向量化 → 余弦相似度检索。

故意不依赖 chromadb / langchain，用最少代码展示 RAG 的核心原理——
方便你真正理解每一步在做什么（面试常被追问 RAG 流程，这套能讲清楚）。
"""
import numpy as np
from pypdf import PdfReader
from llm import embed


def load_pdf(file) -> str:
    """从 PDF 文件对象中提取全部文本。"""
    reader = PdfReader(file)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def split_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """把长文本切成带重叠的小块（chunk）。

    重叠（overlap）是为了避免关键信息正好被切断在两块的交界处。
    """
    text = text.replace("\n", " ")
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return [c for c in chunks if c.strip()]


class SimpleVectorStore:
    """最简向量库：把 chunk 及其向量存在内存里，用余弦相似度检索。"""

    def __init__(self, chunks: list[str]):
        self.chunks = chunks
        self.vectors = np.array(embed(chunks))  # 一次性把所有 chunk 向量化

    def search(self, query: str, top_k: int = 3) -> list[str]:
        """返回与 query 最相关的 top_k 个文本块。"""
        q = np.array(embed([query])[0])
        # 余弦相似度 = 点积 / (各自模长之积)
        sims = self.vectors @ q / (
            np.linalg.norm(self.vectors, axis=1) * np.linalg.norm(q) + 1e-9
        )
        idx = sims.argsort()[::-1][:top_k]  # 相似度从高到低，取前 top_k
        return [self.chunks[i] for i in idx]
