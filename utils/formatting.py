from __future__ import annotations

from html import escape

from utils.catalog_loader import Category, PortfolioProject, Service


PRICE_NOTE = (
    "Цены в каталоге ориентировочные. Диапазон показывает типичную стоимость "
    "задач данного класса. Итоговая стоимость и срок определяются после получения "
    "и оценки технического задания. Сложные интеграции, нестандартная логика и "
    "дополнительные функции рассчитываются отдельно."
)


def h(value: object | None) -> str:
    if value is None or value == "":
        return "—"
    return escape(str(value), quote=False)


def service_card(service: Service) -> str:
    description = service.full_description or service.short_description
    return (
        f"<b>{h(service.title)}</b>\n\n"
        f"{h(description)}\n\n"
        "<b>Ориентировочная стоимость:</b>\n"
        f"{h(service.display_price)}\n\n"
        "Итоговая стоимость зависит от объёма и сложности задачи."
    )


def category_price_list(category: Category, services: list[Service]) -> str:
    lines = [f"<b>💰 {h(category.title)}</b>", ""]
    lines.extend(f"• {h(item.title)} — {h(item.display_price)}" for item in services)
    lines.extend(("", h(PRICE_NOTE)))
    return "\n".join(lines)


def portfolio_card(project: PortfolioProject) -> str:
    text = f"<b>{h(project.title)}</b>\n\n{h(project.short_description)}"
    if project.url:
        text += f'\n\n<a href="{escape(project.url, quote=True)}">Открыть проект</a>'
    return text


def order_summary(data: dict[str, object]) -> str:
    return (
        "<b>📝 Проверьте заявку</b>\n\n"
        f"<b>Услуга:</b>\n{h(data.get('service_title'))}\n\n"
        f"<b>Задача:</b>\n{h(data.get('description'))}\n\n"
        f"<b>Материалы:</b>\n{h(data.get('materials'))}\n\n"
        f"<b>Желаемый срок:</b>\n{h(data.get('desired_deadline'))}\n\n"
        f"<b>Бюджет:</b>\n{h(data.get('budget'))}\n\n"
        f"<b>Дополнительно:</b>\n{h(data.get('comment'))}\n\n"
        f"<i>{h(PRICE_NOTE)}</i>"
    )
