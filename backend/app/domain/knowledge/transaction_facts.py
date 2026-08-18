"""Conservative, page-backed extraction of transaction facts from an announcement.

This module deliberately returns the source block verbatim instead of trying to
turn it into a normalized value.  A keyword hit is not a license to infer a
party, percentage, date, or financial impact that the announcement did not say.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from backend.app.domain.knowledge.models import PersistentDocumentBlock
from backend.app.domain.knowledge.schemas import TransactionFactEvidence, TransactionFactRow

NOT_DISCLOSED = "公告未披露"
MAX_EVIDENCE_PER_FIELD = 3


@dataclass(frozen=True)
class FactRule:
    field: str
    keywords: tuple[str, ...]
    requires_impact_signal: bool = False


FACT_RULES = (
    FactRule("交易类型", ("交易类型", "收购", "购买资产", "重大资产重组", "吸收合并", "资产置换", "股权转让")),
    FactRule("交易对手", ("交易对方", "交易对手", "出售方", "转让方", "受让方", "卖方", "购买方")),
    FactRule("标的公司", ("标的公司", "标的资产", "目标公司", "被收购", "拟收购")),
    FactRule("收购比例", ("收购比例", "持股比例", "取得股权", "购买股权", "收购股权")),
    FactRule("交易对价", ("交易对价", "交易价格", "支付对价", "交易作价", "收购价", "转让价")),
    FactRule("支付方式", ("支付方式", "现金支付", "发行股份", "股份支付", "定向发行")),
    FactRule("资金来源", ("资金来源", "自有资金", "自筹资金", "募集配套资金", "银行贷款", "融资")),
    FactRule("审批条件", ("审批条件", "尚需", "董事会审议", "股东大会审议", "核准", "备案", "证监会", "反垄断")),
    FactRule("公告日期", ("公告日期", "公告日", "披露日期", "披露日")),
    FactRule("预计完成日期", ("预计完成", "预计交割", "计划完成", "完成交割", "预计于")),
    FactRule("对营收的预计影响", ("营业收入", "营收", "主营业务收入"), requires_impact_signal=True),
    FactRule("对利润的预计影响", ("净利润", "利润", "盈利", "业绩"), requires_impact_signal=True),
    FactRule("对现金流的预计影响", ("经营现金流", "现金流量", "现金流"), requires_impact_signal=True),
    FactRule("对负债的预计影响", ("负债", "资产负债率", "偿债"), requires_impact_signal=True),
)

IMPACT_SIGNALS = ("预计", "预期", "将对", "不会对", "影响", "完成后")


def _matches(rule: FactRule, text: str) -> bool:
    if not any(keyword in text for keyword in rule.keywords):
        return False
    return not rule.requires_impact_signal or any(signal in text for signal in IMPACT_SIGNALS)


def _evidence(block: PersistentDocumentBlock) -> TransactionFactEvidence:
    return TransactionFactEvidence(
        page_number=block.page_number,
        block_id=str(block.id),
        text=block.text,
    )


def extract_transaction_facts(blocks: Iterable[PersistentDocumentBlock]) -> list[TransactionFactRow]:
    """Build every row in the fixed table, preserving document/page order."""
    ordered_blocks = sorted(blocks, key=lambda block: (block.page_number, block.id))
    rows: list[TransactionFactRow] = []
    for rule in FACT_RULES:
        evidence = [_evidence(block) for block in ordered_blocks if _matches(rule, block.text)]
        evidence = evidence[:MAX_EVIDENCE_PER_FIELD]
        rows.append(
            TransactionFactRow(
                field=rule.field,
                value=NOT_DISCLOSED if not evidence else "已在公告原文中披露",
                evidence=evidence,
            )
        )
    return rows
