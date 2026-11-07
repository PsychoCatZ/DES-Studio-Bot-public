from aiogram.filters.callback_data import CallbackData


class NavCallback(CallbackData, prefix="nav"):
    action: str


class CategoryCallback(CallbackData, prefix="cat"):
    category_id: str
    view: str


class ServiceCallback(CallbackData, prefix="svc"):
    service_id: str


class PortfolioCallback(CallbackData, prefix="pf"):
    project_id: str


class OrderCallback(CallbackData, prefix="ord"):
    action: str
    ref: str = ""


class ReplyOrderCallback(CallbackData, prefix="reply_order"):
    order_id: int


class ClientReplyOrderCallback(CallbackData, prefix="client_reply"):
    order_id: int


class ClientSelectOrderCallback(CallbackData, prefix="client_select"):
    order_id: int
    client_message_id: int
