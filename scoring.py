"""
结构化评分引擎 (Structured Scoring)
- 数据源无关:核心只吃一个 metrics 字典,缺哪个指标自动跳过并重新归一权重
- 可解释:每个指标的原始值、子分、权重、贡献都暴露出来,不是黑盒
- LLM 层:把结构化打分喂给 DeepSeek,生成自然语言投资评价 + 亮点/风险
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, TypedDict


# ============================================================
# 1. 评分配置(面试时就指着这块讲"我的阈值依据")
#    anchors: [(指标值, 对应0-100分), ...] 之间做线性插值
# ============================================================
@dataclass
class Metric:
    key: str            # metrics 字典里的键
    name: str
    weight: float       # 维度内权重
    anchors: list[tuple[float, float]]
    neg_bad: bool = False   # True 表示负值=亏损/异常,直接给地板分


@dataclass
class Dimension:
    key: str
    name: str
    weight: float       # 总分里的权重
    metrics: list[Metric]


SCHEME: list[Dimension] = [
    Dimension("valuation", "估值", 0.20, [
        Metric("pe_ttm", "PE(TTM)", 0.6,
               [(10, 95), (20, 80), (35, 55), (60, 30), (100, 10)], neg_bad=True),
        Metric("pb", "市净率 PB", 0.4,
               [(1, 90), (2, 75), (4, 50), (8, 25), (15, 10)], neg_bad=True),
    ]),
    Dimension("profit", "盈利能力", 0.25, [
        Metric("roe", "ROE(%)", 0.45,
               [(0, 20), (5, 50), (10, 70), (15, 85), (20, 95), (30, 100)], neg_bad=True),
        Metric("net_margin", "净利率(%)", 0.30,
               [(0, 25), (5, 50), (10, 70), (20, 88), (30, 100)], neg_bad=True),
        Metric("gross_margin", "毛利率(%)", 0.25,
               [(10, 30), (20, 50), (30, 70), (40, 85), (60, 100)]),
    ]),
    Dimension("growth", "成长性", 0.25, [
        Metric("rev_growth", "营收增速 YoY(%)", 0.5,
               [(-20, 10), (0, 40), (10, 65), (20, 80), (40, 95), (60, 100)]),
        Metric("profit_growth", "净利润增速 YoY(%)", 0.5,
               [(-30, 10), (0, 40), (15, 70), (30, 85), (60, 100)]),
    ]),
    Dimension("health", "财务健康", 0.20, [
        Metric("debt_ratio", "资产负债率(%)", 0.6,
               [(20, 95), (40, 80), (55, 65), (70, 45), (85, 25), (95, 10)]),
        Metric("current_ratio", "流动比率", 0.4,
               [(0.5, 20), (1, 50), (1.5, 75), (2, 90), (3, 95)]),
    ]),
    Dimension("momentum", "动量/技术面", 0.10, [
        Metric("ret_60d", "近60日涨跌幅(%)", 0.5,
               [(-30, 20), (-10, 45), (0, 60), (10, 75), (30, 90), (50, 95)]),
        Metric("price_vs_ma20", "现价相对MA20(%)", 0.5,
               [(-15, 25), (-5, 50), (0, 65), (5, 80), (15, 90)]),
    ]),
]

RATING_BANDS = [
    (85, "A", "强烈看好"),
    (70, "B", "看好"),
    (55, "C", "中性"),
    (40, "D", "偏谨慎"),
    (0,  "E", "回避"),
]

CORE_DIMENSIONS = {"valuation", "profit", "growth", "health"}


class ScoreEvaluation(TypedDict):
    """Quality-gated scoring response for callers that need reliable coverage."""

    status: Literal["ok", "insufficient_data"]
    coverage: float
    missing_core_dimensions: list[str]
    missing_metrics: list[str]
    result: dict[str, Any] | None


# ============================================================
# 2. 打分核心
# ============================================================
def _interp(value: float, anchors: list[tuple[float, float]]) -> float:
    a = sorted(anchors, key=lambda x: x[0])
    if value <= a[0][0]:
        return a[0][1]
    if value >= a[-1][0]:
        return a[-1][1]
    for (v0, s0), (v1, s1) in zip(a, a[1:]):
        if v0 <= value <= v1:
            t = (value - v0) / (v1 - v0) if v1 != v0 else 0
            return s0 + t * (s1 - s0)
    return a[-1][1]


def _metric_subscore(m: Metric, value: Any) -> float | None:
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if m.neg_bad and value <= 0:
        return min(s for _, s in m.anchors)   # 亏损/异常 → 地板分
    return round(_interp(value, m.anchors), 1)


def score_stock(metrics: dict[str, Any]) -> dict[str, Any]:
    """metrics 里有哪个算哪个,缺失项不计分,同维度内权重自动重新归一。"""
    dims_out: list[dict[str, Any]] = []
    dim_w_total, total = 0.0, 0.0

    for d in SCHEME:
        sub: list[dict[str, Any]] = []
        w_present = 0.0
        for m in d.metrics:
            s = _metric_subscore(m, metrics.get(m.key))
            if s is None:
                continue
            sub.append({"name": m.name, "value": metrics.get(m.key),
                        "subscore": s, "weight": m.weight})
            w_present += m.weight
        if not sub:                      # 整个维度无数据,跳过
            continue
        for item in sub:                 # 维度内权重归一
            item["weight_norm"] = round(item["weight"] / w_present, 3)
        dim_score = round(sum(i["subscore"] * i["weight_norm"] for i in sub), 1)
        dims_out.append({"name": d.name, "score": dim_score,
                         "weight": d.weight, "metrics": sub})
        dim_w_total += d.weight

    for dimension_out in dims_out:       # 维度权重归一(以防有维度缺失)
        dimension_out["weight_norm"] = round(dimension_out["weight"] / dim_w_total, 3)
        dimension_out["contribution"] = round(
            dimension_out["score"] * dimension_out["weight_norm"], 1
        )
        total += dimension_out["contribution"]
    total = round(total, 1)

    grade, label = next((g, l) for thr, g, l in RATING_BANDS if total >= thr)
    return {"total": total, "grade": grade, "label": label, "dimensions": dims_out}


def _is_valid_metric_value(value: Any) -> bool:
    """Return whether a value can safely participate in numeric scoring."""
    if value is None or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def evaluate_score(metrics: dict[str, Any]) -> ScoreEvaluation:
    """Score only sufficiently complete, finite metric data.

    Invalid scheme values are excluded before delegating to ``score_stock`` so
    legacy callers keep their original semantics while new callers cannot get
    a rating from incomplete data.
    """
    valid_metrics: dict[str, Any] = {}
    missing_metrics: list[str] = []
    missing_core_dimensions: list[str] = []
    coverage = 0.0

    for dimension in SCHEME:
        dimension_has_valid_metric = False
        for metric in dimension.metrics:
            value = metrics.get(metric.key)
            if not _is_valid_metric_value(value):
                missing_metrics.append(metric.key)
                continue
            assert value is not None
            valid_metrics[metric.key] = float(value)
            coverage += dimension.weight * metric.weight
            dimension_has_valid_metric = True
        if dimension.key in CORE_DIMENSIONS and not dimension_has_valid_metric:
            missing_core_dimensions.append(dimension.key)

    coverage = round(coverage, 10)
    if coverage < 0.80 or missing_core_dimensions:
        return {
            "status": "insufficient_data",
            "coverage": coverage,
            "missing_core_dimensions": missing_core_dimensions,
            "missing_metrics": missing_metrics,
            "result": None,
        }

    return {
        "status": "ok",
        "coverage": coverage,
        "missing_core_dimensions": [],
        "missing_metrics": missing_metrics,
        "result": score_stock(valid_metrics),
    }


# ============================================================
# 3. LLM 解读层(复用你现有的 DeepSeek 配置)
# ============================================================
def build_explain_prompt(result: dict, name: str = "该标的") -> str:
    lines = [f"{name} 综合评分 {result['total']}({result['grade']}/{result['label']}),各维度:"]
    for d in result["dimensions"]:
        lines.append(f"- {d['name']}:{d['score']}(权重{d['weight_norm']},贡献{d['contribution']})")
        for m in d["metrics"]:
            lines.append(f"    · {m['name']}={m['value']} → {m['subscore']}分")
    lines.append("\n请基于以上量化评分,输出:\n"
                 "1) 一句话定性结论\n2) 三个核心亮点\n3) 三个主要风险\n"
                 "只依据数据,不要编造没给出的指标。")
    return "\n".join(lines)


def explain_score(result: dict, client, name="该标的", model="deepseek-chat") -> str:
    """client = 你项目里已经配好的 OpenAI 兼容 DeepSeek 客户端"""
    resp = client.chat.completions.create(
        model=model,
        temperature=0.3,
        messages=[
            {"role": "system", "content": "你是严谨的卖方分析师,只基于给定数据点评。"},
            {"role": "user", "content": build_explain_prompt(result, name)},
        ],
    )
    return resp.choices[0].message.content


# ============================================================
# 4. 自测(用假数据跑通)
# ============================================================
if __name__ == "__main__":
    import json
    demo = {
        "pe_ttm": 18.5, "pb": 2.3, "roe": 16.2, "net_margin": 12.5,
        "gross_margin": 38.0, "rev_growth": 22.0, "profit_growth": 28.0,
        "debt_ratio": 45.0, "current_ratio": 1.8,
        "ret_60d": 8.0, "price_vs_ma20": 3.5,
    }
    print(json.dumps(score_stock(demo), ensure_ascii=False, indent=2))
