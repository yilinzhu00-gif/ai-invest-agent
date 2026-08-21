export type WatchlistStock = {
  symbol: string;
  name: string;
  price: string;
  change: string;
  tone: "positive" | "negative" | "neutral";
  thesis: string;
  sector: string;
  updated: string;
};

export const WATCHLIST: WatchlistStock[] = [
  {
    symbol: "AAPL",
    name: "Apple Inc.",
    price: "$227.16",
    change: "+1.24%",
    tone: "positive",
    thesis: "服务业务与设备生态继续提供现金流韧性",
    sector: "消费电子 · 软件服务",
    updated: "08:30 ET",
  },
  {
    symbol: "NVDA",
    name: "NVIDIA Corp.",
    price: "$181.62",
    change: "+2.87%",
    tone: "positive",
    thesis: "AI 基础设施需求强劲，但估值对执行力更敏感",
    sector: "半导体 · AI 基础设施",
    updated: "08:30 ET",
  },
  {
    symbol: "TSLA",
    name: "Tesla, Inc.",
    price: "$338.52",
    change: "−0.62%",
    tone: "negative",
    thesis: "自动驾驶期权仍大，但短期交付与利润率承压",
    sector: "汽车 · 清洁能源",
    updated: "08:30 ET",
  },
];

export const REPORT = {
  symbol: "AAPL",
  name: "Apple Inc.",
  subtitle: "生态型现金流复利，等待服务增长重新加速",
  score: "7.8",
  stance: "关注",
  asOf: "2026-08-21",
  metrics: [
    { label: "当前价格", value: "$227.16", detail: "+1.24% 今日", tone: "positive" },
    { label: "市值", value: "$3.37T", detail: "大型股", tone: "neutral" },
    { label: "市盈率", value: "34.8x", detail: "相对历史偏高", tone: "warning" },
    { label: "研究评分", value: "7.8 / 10", detail: "中高置信度", tone: "positive" },
  ],
  investmentLogic: [
    "设备 installed base 与服务业务形成高切换成本，硬件周期波动被订阅和支付收入部分平滑。",
    "AI 功能逐步进入系统级体验，若能带来换机与服务渗透率提升，增长质量有望改善。",
    "资本回报纪律和强劲自由现金流为回购提供支撑，但估值已经反映了一部分执行成果。",
  ],
  financials: [
    { label: "收入增长", value: "+6.2%", note: "同比，示例数据" },
    { label: "毛利率", value: "46.8%", note: "服务占比提升" },
    { label: "自由现金流", value: "$108B", note: "过去 12 个月" },
  ],
  risks: [
    "高端智能手机需求放缓，换机周期拉长可能使硬件收入低于预期。",
    "监管与 App Store 费率变化可能压缩服务业务的利润率。",
    "估值较高，若 AI 功能转化为商业结果的节奏不及预期，股价波动会被放大。",
  ],
  sources: [
    { label: "公司 10-K / 10-Q", detail: "财务与风险披露 · 2026-08-21" },
    { label: "公开行情快照", detail: "价格与估值字段 · 2026-08-21" },
    { label: "研究员判断", detail: "基于上述来源的结构化推理" },
  ],
  bull: ["服务收入增速恢复到双位数", "AI 设备周期带来换机上行", "回购持续提升每股现金流"],
  bear: ["估值压缩抵消盈利增长", "监管影响服务抽成", "硬件需求进入低增长区间"],
};

export function getWatchlistStock(symbol: string): WatchlistStock {
  return WATCHLIST.find((stock) => stock.symbol === symbol) ?? WATCHLIST[0];
}
