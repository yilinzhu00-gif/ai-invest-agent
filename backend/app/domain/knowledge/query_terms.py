"""Small deterministic normalization for evidence retrieval queries."""

import re

_QUESTION_SUFFIXES = ("是多少", "是什么", "是啥", "吗", "？", "?")
_LEADING_DOCUMENT_CONTEXT = re.compile(r"^(?:这份|该)?(?:公告|研报|报告)(?:对|中|里)?\s*")
_NATURAL_LANGUAGE_CONNECTORS = re.compile(
    r"(?:请问|请|帮我|告诉我|这份|该|本次|公告|研报|报告|年报|半年报|"
    r"关于|披露|提到|说明|显示|是否|有没有|有无|是什么|多少|怎么样|如何|吗|呢|在|中|里|的)"
)
_FINANCIAL_PHRASES = (
    "归属于上市公司股东的净利润",
    "扣除非经常性损益的净利润",
    "归母净利润",
    "净利润",
    "营业收入",
    "营业利润",
    "毛利率",
    "经营现金流",
    "每股收益",
    "盈利预测",
    "目标价",
    "预测",
    "估值",
    "对价",
    "分红",
    "回购",
    "半年度",
)


def retrieval_query_terms(query: str) -> list[str]:
    """Keep factual Chinese key phrases without requiring a whole-sentence match.

    The result is used only to retrieve candidate excerpts.  It never makes an
    unsupported answer eligible for automatic completion; the Validator and
    Reviewer still decide whether a retrieved excerpt can support a conclusion.
    """
    normalized = re.sub(r"\s+", " ", query).strip()
    for suffix in _QUESTION_SUFFIXES:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip()
            break
    normalized = _LEADING_DOCUMENT_CONTEXT.sub("", normalized)
    separated = [term.lower() for term in normalized.split() if term]
    if len(separated) > 1:
        compact = "".join(separated)
        phrases = [phrase for phrase in _FINANCIAL_PHRASES if phrase in compact]
        return list(dict.fromkeys([*separated, *phrases]))

    candidate = separated[0] if separated else ""
    if not candidate:
        return []
    phrases = [phrase for phrase in _FINANCIAL_PHRASES if phrase in candidate]
    if phrases:
        return list(dict.fromkeys([candidate, *phrases]))

    # A Chinese question normally has no spaces.  Keeping that whole sentence
    # alone makes literal retrieval unnecessarily brittle for factual terms
    # outside the small financial-phrase list above.  Extract only the content
    # fragments delimited by question scaffolding; these are still candidates,
    # not evidence or conclusions.  The downstream citation Validator and
    # Reviewer remain the authority for whether a retrieved block is usable.
    fragments = [
        fragment.strip().lower()
        for fragment in _NATURAL_LANGUAGE_CONNECTORS.split(candidate)
        if len(re.sub(r"\d{2,4}年?", "", fragment).strip()) >= 3
    ]
    return list(dict.fromkeys([candidate, *fragments]))
