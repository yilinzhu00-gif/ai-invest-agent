"""Translate an observed market snapshot into immutable Run evidence and UI data."""

from backend.app.agents.schemas import Citation
from backend.app.tools.market_snapshot import MarketSnapshotOutput


def market_snapshot_citation(snapshot: MarketSnapshotOutput) -> Citation:
    recent = "；".join(
        f"{item.date.isoformat()} 收盘 {item.close:g}" for item in snapshot.recent_closes
    )
    optional = []
    if snapshot.change_percent is not None:
        optional.append(f"当日涨跌幅 {snapshot.change_percent:g}%")
    if snapshot.high is not None and snapshot.low is not None:
        optional.append(f"当日区间 {snapshot.low:g}–{snapshot.high:g}")
    text = (
        f"{snapshot.symbol} 最近交易日市场快照：截至 {snapshot.as_of_date.isoformat()} 收盘 {snapshot.close:g}；"
        f"近 {len(snapshot.recent_closes)} 个交易日区间变动 "
        f"{snapshot.period_change_percent if snapshot.period_change_percent is not None else '不可用'}%；"
        f"{recent}。"
    )
    if optional:
        text += "；" + "；".join(optional) + "。"
    return Citation(
        id=f"market-snapshot-{snapshot.symbol}-{snapshot.as_of_date.isoformat()}",
        source=snapshot.source,
        locator=f"symbol={snapshot.symbol}; as_of={snapshot.as_of_date.isoformat()}",
        text=text,
    )


def market_result_payload(snapshot: MarketSnapshotOutput, summary: str) -> dict[str, object]:
    return {
        "symbol": snapshot.symbol,
        "summary": summary,
        "snapshot": snapshot.model_dump(mode="json"),
        "source": snapshot.source,
        "boundary": "该结果仅整理已取得的历史日线快照，不预测未来走势，也不构成投资建议。",
    }
