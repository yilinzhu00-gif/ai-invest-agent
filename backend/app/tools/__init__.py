"""Fixed read-only tools for controlled Agent execution."""

from backend.app.tools.financial_tool import get_financial_report
from backend.app.tools.news_tool import search_news
from backend.app.tools.search_tool import search_web
from backend.app.tools.stock_tool import get_stock_price

__all__ = ["get_financial_report", "get_stock_price", "search_news", "search_web"]
