from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent, Message

from config import BASE_DIR, Config
from database import Database
from handlers import (
    admin_reply_router,
    admin_reply_fallback_router,
    catalog_router,
    conversation_priority_router,
    conversation_router,
    order_router,
    portfolio_router,
    referrals_router,
    start_router,
)
from utils.catalog_loader import Catalog, Portfolio, load_catalog, load_portfolio


logger = logging.getLogger(__name__)


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(start_router)
    dispatcher.include_router(referrals_router)
    dispatcher.include_router(admin_reply_router)
    dispatcher.include_router(conversation_priority_router)
    dispatcher.include_router(catalog_router)
    dispatcher.include_router(portfolio_router)
    dispatcher.include_router(order_router)
    dispatcher.include_router(conversation_router)
    dispatcher.include_router(admin_reply_fallback_router)
    dispatcher.errors.register(handle_error)
    return dispatcher


async def handle_error(event: ErrorEvent) -> bool:
    logger.error(
        "Unhandled error while processing update %s",
        event.update.update_id,
        exc_info=(type(event.exception), event.exception, event.exception.__traceback__),
    )
    update = event.update
    try:
        if update.callback_query:
            try:
                await update.callback_query.answer()
            except Exception:
                logger.debug("Could not acknowledge failed callback", exc_info=True)
            if isinstance(update.callback_query.message, Message):
                await update.callback_query.message.answer(
                    "Произошла техническая ошибка.\n"
                    "Попробуйте повторить действие или вернитесь в главное меню."
                )
        elif update.message:
            await update.message.answer(
                "Произошла техническая ошибка.\n"
                "Попробуйте повторить действие или вернитесь в главное меню."
            )
    except Exception:
        logger.exception("Could not send the user-facing error message")
    return True


def load_application_data() -> tuple[Catalog, Portfolio]:
    return (
        load_catalog(BASE_DIR / "data" / "catalog.json"),
        load_portfolio(BASE_DIR / "data" / "portfolio.json"),
    )


def run_check() -> int:
    config = Config.from_env(require_secrets=False)
    catalog, portfolio = load_application_data()
    database = Database(config.database_path)
    database.initialize()
    build_dispatcher()
    print(
        "Self-check passed: "
        f"{len(catalog.categories)} categories, "
        f"{len(catalog.services)} services, "
        f"{len(portfolio.projects)} portfolio projects; "
        f"database: {config.database_path}"
    )
    return 0


async def main() -> None:
    config = Config.from_env()
    catalog, portfolio = load_application_data()
    database = Database(config.database_path)
    database.initialize()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = build_dispatcher()
    logger.info(
        "Starting DES Studio bot: %d categories, %d services, %d portfolio projects",
        len(catalog.categories),
        len(catalog.services),
        len(portfolio.projects),
    )
    try:
        await dispatcher.start_polling(
            bot,
            catalog=catalog,
            portfolio=portfolio,
            database=database,
            config=config,
            project_root=BASE_DIR,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    parser = argparse.ArgumentParser(description="DES Studio Telegram Bot")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate data, database, imports and dispatcher without connecting to Telegram",
    )
    args = parser.parse_args()
    try:
        if args.check:
            raise SystemExit(run_check())
        asyncio.run(main())
    except (ValueError, OSError) as exc:
        logger.error("Startup failed: %s", exc)
        raise SystemExit(1) from exc
