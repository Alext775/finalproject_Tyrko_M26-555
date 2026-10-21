"""Тесты моделей"""

import unittest
from typing import cast

from valutatrade_hub.core.currencies import (
    CryptoCurrency,
    FiatCurrency,
    get_currency,
)
from valutatrade_hub.core.exceptions import (
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.models import Portfolio, User, Wallet


class ModelTests(unittest.TestCase):
    """Проверки User, Wallet, Portfolio и Currency"""

    def setUp(self) -> None:
        """Создать тестового пользователя"""
        self.user = User.create(1, "alice", "1234")

    def test_password(self) -> None:
        """Проверить хеширование и изменение пароля"""
        self.assertTrue(self.user.verify_password("1234"))
        self.assertFalse(self.user.verify_password("wrong"))

        self.assertNotIn(
            "hashed_password",
            self.user.get_user_info(),
        )

        self.user.change_password("newpass")
        self.assertTrue(self.user.verify_password("newpass"))

        with self.assertRaises(ValueError):
            self.user.change_password("123")

        restored = User.from_dict(self.user.to_dict())
        self.assertEqual(restored.username, "alice")

    def test_wallet(self) -> None:
        """Проверить пополнение, снятие и валидацию"""
        wallet = Wallet("BTC")

        invalid_amounts: list[object] = [
            -1,
            0,
            True,
            float("nan"),
            float("inf"),
            "3",
        ]

        for value in invalid_amounts:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    wallet.deposit(cast(float, value))

        wallet.deposit(0.5)
        wallet.withdraw(0.25)

        self.assertAlmostEqual(wallet.balance, 0.25)

        with self.assertRaises(InsufficientFundsError):
            wallet.withdraw(1.0)

        with self.assertRaises(ValueError):
            wallet.balance = -1

    def test_portfolio(self) -> None:
        """Проверить создание кошельков и оценку портфеля"""
        portfolio = Portfolio(self.user)

        btc_wallet = portfolio.add_currency("BTC")

        self.assertIs(
            btc_wallet,
            portfolio.add_currency("BTC"),
        )

        usd_wallet = portfolio.add_currency("USD")
        usd_wallet.deposit(100)

        btc_wallet.deposit(0.01)

        self.assertAlmostEqual(
            portfolio.get_total_value(),
            690.0,
        )

        copied = portfolio.wallets
        copied.clear()

        self.assertEqual(
            len(portfolio.wallets),
            2,
        )

        with self.assertRaises(AttributeError):
            object.__setattr__(portfolio, "user", self.user)

    def test_currencies(self) -> None:
        """Проверить иерархию и реестр валют"""
        self.assertIsInstance(
            get_currency("USD"),
            FiatCurrency,
        )

        self.assertIsInstance(
            get_currency("BTC"),
            CryptoCurrency,
        )

        self.assertIn(
            "Issuing:",
            get_currency("USD").get_display_info(),
        )

        with self.assertRaises(CurrencyNotFoundError):
            get_currency("ABC")

        with self.assertRaises(ValueError):
            get_currency("btc")


if __name__ == "__main__":
    unittest.main()
