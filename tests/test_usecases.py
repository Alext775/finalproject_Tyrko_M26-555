"""Тесты регистрации, торговли и кеша"""

import json
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from typing import cast
from unittest.mock import patch

from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    InsufficientFundsError,
)
from valutatrade_hub.core.usecases import UseCases
from valutatrade_hub.core.utils import to_utc_iso, utc_now
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.storage import RateSnapshot


class UseCasesTests(unittest.TestCase):
    """Проверки бизнес-логики во временной директории"""

    def setUp(self) -> None:
        """Подготовить временное хранилище"""
        self.temp = tempfile.TemporaryDirectory()

        self.env_patch = patch.dict(
            os.environ,
            {"VALUTATRADE_DATA_DIR": self.temp.name},
        )

        self.env_patch.start()
        SettingsLoader().reload()

        self.core = UseCases()
        self._save_rates(to_utc_iso())

    def tearDown(self) -> None:
        """Восстановить настройки после теста"""
        self.env_patch.stop()
        SettingsLoader().reload()
        self.temp.cleanup()

    def _save_rates(self, timestamp: str) -> None:
        """Сохранить тестовые обменные курсы"""
        rates: RateSnapshot = {
            "pairs": {
                "BTC_USD": {
                    "rate": 60000.0,
                    "updated_at": timestamp,
                    "source": "test",
                },
                "EUR_USD": {
                    "rate": 1.25,
                    "updated_at": timestamp,
                    "source": "test",
                },
            },
            "last_refresh": timestamp,
        }

        Path(self.temp.name, "rates.json").write_text(
            json.dumps(rates),
            encoding="utf-8",
        )

    def test_trade_cycle(self) -> None:
        """Проверить полный цикл покупки и продажи"""
        registered = self.core.register("alice", "1234")
        user_id = cast(int, registered["user_id"])

        self.assertEqual(
            self.core.login("alice", "1234")["user_id"],
            user_id,
        )

        self.core.deposit(user_id, 5000)

        bought = self.core.buy(user_id, "BTC", 0.05)

        self.assertAlmostEqual(bought["cost"], 3000)
        self.assertAlmostEqual(bought["usd_after"], 2000)

        sold = self.core.sell(user_id, "BTC", 0.01)

        self.assertAlmostEqual(sold["revenue"], 600)
        self.assertAlmostEqual(sold["after"], 0.04)

        new_core = UseCases()

        self.assertAlmostEqual(
            new_core.show_portfolio(user_id)["total"],
            5000,
        )

        with self.assertRaises(InsufficientFundsError):
            self.core.sell(user_id, "BTC", 1)

        with self.assertRaises(InsufficientFundsError):
            self.core.buy(user_id, "BTC", 100)

    def test_authentication_errors(self) -> None:
        """Проверить ошибки регистрации и авторизации"""
        self.core.register("alice", "1234")

        with self.assertRaisesRegex(ValueError, "уже занято"):
            self.core.register("alice", "1234")

        with self.assertRaisesRegex(ValueError, "Неверный пароль"):
            self.core.login("alice", "wrong")

    def test_rates_and_ttl(self) -> None:
        """Проверить конвертацию и срок актуальности кеша"""
        rate = self.core.get_rate("USD", "BTC")["rate"]

        self.assertAlmostEqual(rate, 1 / 60000)

        rate = self.core.get_rate("BTC", "EUR")["rate"]

        self.assertAlmostEqual(rate, 48000)

        old_time = utc_now() - timedelta(hours=1)
        self._save_rates(to_utc_iso(old_time))

        with self.assertRaisesRegex(ApiRequestError, "устарел"):
            self.core.get_rate("BTC", "USD")

        self.assertEqual(
            len(self.core.show_rates(top=1)["rows"]),
            1,
        )

    def test_invalid_currency(self) -> None:
        """Проверить обработку некорректной валюты"""
        registered = self.core.register(
            "alice",
            "1234",
        )

        user_id = cast(int, registered["user_id"])

        self.core.deposit(user_id, 1000)

        with self.assertRaises(ValueError):
            self.core.buy(user_id, "usd", 1)

        self.assertEqual(
            len(self.core.show_portfolio(user_id)["wallets"]),
            1,
        )

    def test_register_storage_failure(self) -> None:
        """Проверить восстановление данных при ошибке записи"""
        original_write = self.core.db.write_json

        def failing_write(
            settings_key: str,
            value: object,
        ) -> None:
            """Имитировать сбой сохранения портфеля"""
            if settings_key == "portfolios_file":
                raise OSError("Тестовый сбой записи")

            original_write(settings_key, value)

        with patch.object(
            self.core.db,
            "write_json",
            side_effect=failing_write,
        ):
            with self.assertRaises(OSError):
                self.core.register("alice", "1234")

        users = self.core.db.read_json("users_file", [])

        self.assertEqual(users, [])


if __name__ == "__main__":
    unittest.main()
