import unittest

from callbacks import CategoryCallback, NavCallback, OrderCallback, ServiceCallback
from config import BASE_DIR
from keyboards.catalog import category_keyboard, prices_keyboard, service_keyboard
from keyboards.main import main_menu_keyboard
from keyboards.order import confirmation_keyboard
from utils.catalog_loader import load_catalog


def callback_values(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class KeyboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(BASE_DIR / "data" / "catalog.json")

    def test_main_menu_and_all_categories_have_working_targets(self) -> None:
        values = callback_values(main_menu_keyboard(self.catalog))
        self.assertEqual(11, len(values))
        referral_callback = NavCallback(action="referral_link").pack()
        self.assertIn(referral_callback, values)
        for category in self.catalog.categories:
            expected = CategoryCallback(category_id=category.id, view="catalog").pack()
            self.assertIn(expected, values)
            category_values = callback_values(category_keyboard(self.catalog, category.id))
            for service in self.catalog.services_for_category(category.id):
                self.assertIn(ServiceCallback(service_id=service.id).pack(), category_values)
            self.assertIn(NavCallback(action="home").pack(), category_values)

    def test_price_service_and_confirmation_navigation(self) -> None:
        price_values = callback_values(prices_keyboard(self.catalog))
        self.assertIn(NavCallback(action="home").pack(), price_values)
        service = self.catalog.get_service("telegram-bot")
        service_values = callback_values(service_keyboard(service))
        self.assertIn(OrderCallback(action="start", ref="telegram-bot").pack(), service_values)
        confirm_values = callback_values(confirmation_keyboard())
        for action in ("send", "restart", "back", "cancel"):
            self.assertIn(OrderCallback(action=action).pack(), confirm_values)


if __name__ == "__main__":
    unittest.main()
