"""Тесты командного интерфейса."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from valutatrade_hub.cli.interface import WalletCLI
from valutatrade_hub.core.utils import to_utc_iso
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.updater import UpdateResult


class CLITests(unittest.TestCase):
    """Проверка команд и сообщений."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()

        self.env_patch = patch.dict(
            os.environ,
            {"VALUTATRADE_DATA_DIR": self.temp.name},
        )

        self.env_patch.start()
        SettingsLoader().reload()

        self.cli = WalletCLI()

    def tearDown(self) -> None:
        self.env_patch.stop()
        SettingsLoader().reload()
        self.temp.cleanup()

    def command(self, line: str) -> str:
        """Выполнить команду и захватить вывод."""
        output = io.StringIO()

        with redirect_stdout(output):
            self.assertTrue(self.cli.execute(line))

        return output.getvalue()

    def test_session(self) -> None:
        result = self.command("deposit --amount 100")
        self.assertIn("Сначала выполните login", result)

        result = self.command("register --username alice --password 1234")
        self.assertIn("зарегистрирован", result)

        result = self.command("login --username alice --password 1234")
        self.assertIn("Вы вошли", result)

        result = self.command("deposit --amount 100")
        self.assertIn("USD пополнен", result)

        result = self.command("show-portfolio")
        self.assertIn("ИТОГО", result)

        result = self.command("buy --amount bad")
        self.assertIn("Неверные аргументы", result)

        result = self.command("logout")
        self.assertIn("Вы вышли", result)

        self.assertFalse(self.cli.execute("exit"))

    def test_trading_and_rates(self) -> None:
        """Проверить торговлю и получение курсов через CLI"""
        timestamp = to_utc_iso()

        self.cli.usecases.db.write_json(
            "rates_file",
            {
                "pairs": {
                    "BTC_USD": {
                        "rate": 60000.0,
                        "updated_at": timestamp,
                        "source": "test",
                    },
                },
                "last_refresh": timestamp,
            },
        )

        self.command("register --username trader --password 1234")
        self.command("login --username trader --password 1234")
        self.command("deposit --amount 10000")

        purchase = self.command("buy --currency BTC --amount 0.05")
        self.assertIn("Покупка выполнена", purchase)

        sale = self.command("sell --currency BTC --amount 0.01")
        self.assertIn("Продажа выполнена", sale)

        portfolio = self.command("show-portfolio")
        self.assertIn("BTC", portfolio)
        self.assertIn("ИТОГО", portfolio)

        quote = self.command("get-rate --from BTC --to USD")
        self.assertIn("60000", quote)

        rates = self.command("show-rates --currency BTC")
        self.assertIn("BTC_USD", rates)

        error = self.command("sell --currency BTC --amount 100")
        self.assertIn("Недостаточно средств", error)

    def test_update_rates_command(self) -> None:
        """Проверить вызов обновления курсов из CLI"""
        fake_result: UpdateResult = {
            "updated": 3,
            "failures": {},
            "last_refresh": to_utc_iso(),
        }

        with patch(
            "valutatrade_hub.cli.interface.RatesUpdater.create_default"
        ) as create_updater:
            create_updater.return_value.run_update.return_value = fake_result

            output = self.command("update-rates")

        self.assertIn("Обновлено курсов: 3", output)


if __name__ == "__main__":
    unittest.main()
