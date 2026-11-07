from handlers.admin_reply import (
    fallback_router as admin_reply_fallback_router,
    router as admin_reply_router,
)
from handlers.catalog import router as catalog_router
from handlers.conversation import (
    priority_router as conversation_priority_router,
    router as conversation_router,
)
from handlers.order import router as order_router
from handlers.portfolio import router as portfolio_router
from handlers.referrals import router as referrals_router
from handlers.start import router as start_router

__all__ = [
    "start_router", "referrals_router", "admin_reply_router", "catalog_router",
    "portfolio_router", "order_router", "conversation_priority_router",
    "conversation_router",
    "admin_reply_fallback_router",
]
