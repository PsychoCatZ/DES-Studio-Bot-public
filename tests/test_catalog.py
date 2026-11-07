from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from config import BASE_DIR
from utils.catalog_loader import DataValidationError, load_catalog, load_portfolio
from utils.formatting import PRICE_NOTE, category_price_list, order_summary, service_card


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog_path = BASE_DIR / "data" / "catalog.json"
        self.catalog = load_catalog(self.catalog_path)

    def test_complete_catalog_and_portfolio_load(self) -> None:
        self.assertEqual(7, len(self.catalog.categories))
        self.assertEqual(38, len(self.catalog.services))
        self.assertTrue(all(self.catalog.services_for_category(item.id) for item in self.catalog.categories))
        portfolio = load_portfolio(BASE_DIR / "data" / "portfolio.json")
        self.assertEqual(
            ["Демо: сайт", "Демо: бот", "Демо: автоматизация", "Демо: интеграция", "Демо: интерфейс"],
            [item.title for item in portfolio.projects],
        )

    def test_new_json_service_appears_without_python_change(self) -> None:
        raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        raw["services"].append(
            {
                "id": "test-service",
                "category_id": "web",
                "title": "Тестовая услуга",
                "short_description": "Проверка data-driven каталога.",
                "price_from": 1,
                "price_to": 2,
                "price_text": "1–2 ₽",
                "active": True,
                "sort_order": 999,
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            changed = load_catalog(path)
        self.assertEqual("Тестовая услуга", changed.get_service("test-service").title)
        self.assertIn("test-service", [item.id for item in changed.services_for_category("web")])

    def test_invalid_reference_is_rejected(self) -> None:
        raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        raw["services"][0]["category_id"] = "missing"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(DataValidationError):
                load_catalog(path)

    def test_price_note_and_html_escaping(self) -> None:
        category = self.catalog.get_category("bots")
        text = category_price_list(category, self.catalog.services_for_category("bots"))
        self.assertIn(PRICE_NOTE, text)
        summary = order_summary(
            {
                "service_title": "<div>",
                "description": "A & B > C",
                "materials": "нет",
            }
        )
        self.assertIn("&lt;div&gt;", summary)
        self.assertIn("A &amp; B &gt; C", summary)
        self.assertNotIn("<div>", summary)

    def test_all_catalog_messages_fit_telegram_limit(self) -> None:
        for category in self.catalog.categories:
            price_text = category_price_list(
                category, self.catalog.services_for_category(category.id)
            )
            self.assertLessEqual(len(price_text), 4096)
        for service in self.catalog.services:
            self.assertLessEqual(len(service_card(service)), 4096)


if __name__ == "__main__":
    unittest.main()
