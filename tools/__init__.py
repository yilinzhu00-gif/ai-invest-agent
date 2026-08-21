"""Public Phase 1 tool entry points.

The application keeps the canonical implementations under ``backend.app``;
these short imports make the requested ``tools.*`` layout usable by scripts
and notebooks without bypassing the application contracts.
"""

from backend.app.tools.financial_tool import get_financial_report
from backend.app.tools.news_tool import search_news
from backend.app.tools.search_tool import search_web
from backend.app.tools.stock_tool import get_stock_price

__all__ = ["get_financial_report", "get_stock_price", "search_news", "search_web"]
