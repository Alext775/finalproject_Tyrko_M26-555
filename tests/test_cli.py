"""Тесты командного интерфейса."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from valutatrade_hub.cli.interface import WalletCLI
from valutatrade_hub.infra.settings import SettingsLoader


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


if __name__ == "__main__":
    unittest.main()
