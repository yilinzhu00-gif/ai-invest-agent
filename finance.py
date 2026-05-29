"""金融数据获取与技术指标计算（基于 akshare，数据免费、无需 token）。"""
import akshare as ak
import pandas as pd
import time


def get_stock_history(code: str, days: int = 120) -> pd.DataFrame:
    """获取 A 股个股近一段时间的日线行情（前复权）。

    code: 6 位股票代码，如 '600519'(贵州茅台)、'000001'(平安银行)
    days: 返回最近多少个交易日
    """
    last_err = None
    for _ in range(3):                      # 偶发断连就重试，最多 3 次
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            break
        except Exception as e:
            last_err = e
            time.sleep(1)
    else:
        raise last_err

    df = df.rename(columns={
        "日期": "date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "volume",
    })
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").tail(days).reset_index(drop=True)
    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算常用技术指标：MA5 / MA20 / RSI14。"""
    df = df.copy()
    df["MA5"] = df["close"].rolling(5).mean()
    df["MA20"] = df["close"].rolling(20).mean()
    df["RSI14"] = _rsi(df["close"], 14)
    return df


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """相对强弱指标 RSI（衡量超买/超卖）。"""
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - 100 / (1 + rs)


def snapshot_text(df: pd.DataFrame, code: str) -> str:
    """把行情数据浓缩成一段文字，喂给 LLM 做解读。"""
    latest, first = df.iloc[-1], df.iloc[0]
    pct = (latest["close"] - first["close"]) / first["close"] * 100
    return (
        f"股票代码 {code}，区间 {df['date'].iloc[0].date()} 至 {latest['date'].date()}。\n"
        f"最新收盘价 {latest['close']:.2f}，区间涨跌幅 {pct:+.2f}%。\n"
        f"MA5={latest['MA5']:.2f}，MA20={latest['MA20']:.2f}，RSI14={latest['RSI14']:.1f}。\n"
        f"区间最高 {df['high'].max():.2f}，最低 {df['low'].min():.2f}，"
        f"最新成交量 {latest['volume']:.0f}。"
    )


def get_metrics(code: str) -> dict:
    """为「结构化评分」凑齐估值/盈利/成长/财务健康/动量等指标。

    缺哪个不影响——评分引擎会自动跳过缺失项并重新归一权重。
    （此函数保持纯数据层，不依赖 streamlit；取数失败的维度静默跳过。）
    """
    m = {}

    # --- 估值：实时 PE(TTM) / PB ---
    try:
        ind = ak.stock_a_indicator_lg(symbol=code).sort_values("trade_date")
        last = ind.iloc[-1]
        m["pe_ttm"] = float(last["pe_ttm"])
        m["pb"] = float(last["pb"])
    except Exception:
        pass

    # --- 财务指标：用「模糊找列」扛 akshare 版本差异 ---
    try:
        fin = ak.stock_financial_analysis_indicator(symbol=code)
        date_col = next((c for c in fin.columns if "日期" in c or "date" in c.lower()), None)
        if date_col:
            fin = fin.sort_values(date_col)
        row = fin.iloc[-1]   # 最新一期

        def pick(*keywords):
            for col in fin.columns:
                if any(k in col for k in keywords):
                    try:
                        return float(row[col])
                    except (TypeError, ValueError):
                        return None
            return None

        m["roe"]           = pick("净资产收益率")
        m["net_margin"]    = pick("销售净利率", "净利率")
        m["gross_margin"]  = pick("销售毛利率", "毛利率")
        m["debt_ratio"]    = pick("资产负债率")
        m["current_ratio"] = pick("流动比率")
        m["rev_growth"]    = pick("主营业务收入增长率", "营业总收入", "收入增长")
        m["profit_growth"] = pick("净利润增长率", "净利润同比")
    except Exception:
        pass

    # --- 动量：近 60 日涨跌幅 + 现价相对 MA20 ---
    try:
        hist = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq").tail(90)
        close = hist["收盘"].astype(float).reset_index(drop=True)
        if len(close) >= 60:
            m["ret_60d"] = round((close.iloc[-1] / close.iloc[-60] - 1) * 100, 2)
        ma20 = close.tail(20).mean()
        m["price_vs_ma20"] = round((close.iloc[-1] / ma20 - 1) * 100, 2)
    except Exception:
        pass

    return {k: v for k, v in m.items() if v is not None}
