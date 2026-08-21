"""Stock API compatibility boundary.

Market data is implemented by ``api.v1.market_data`` today.  Keeping this
module as the domain entry point lets clients migrate to the target layout
without moving the already-tested v1 handlers in one large change.
"""

from backend.app.api.v1.market_data import router

__all__ = ["router"]

