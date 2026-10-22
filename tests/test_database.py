
"""Тесты JSON-хранилища"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader


class DatabaseTests(unittest.TestCase):
    """Проверки чтения, записи и обработки ошибок"""

    def setUp(self) -> None:
        """Создать временную директорию"""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        environment_patch = patch.dict(
            os.environ,
            {"VALUTATRADE_DATA_DIR": self.temp.name},
        )

        environment_patch.start()
        self.addCleanup(SettingsLoader().reload)
        self.addCleanup(environment_patch.stop)

        SettingsLoader().reload()
        self.db = DatabaseManager()

    def test_initialize_files(self) -> None:
        """Проверить создание необходимых JSON-файлов"""
        self.db.initialize_files()

        directory = Path(self.temp.name)

        for filename in (
            "users.json",
            "portfolios.json",
            "rates.json",
            "exchange_rates.json",
        ):
            with self.subTest(filename=filename):
                self.assertTrue(
                    (directory / filename).exists()
                )

    def test_corrupted_json(self) -> None:
        """Проверить обработку поврежденного JSON"""
        path = Path(self.temp.name) / "users.json"
        path.write_text("{broken json", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Поврежден"):
            self.db.read_json("users_file", [])

    def test_failed_atomic_write(self) -> None:
        """Проверить сохранение старых данных при сбое записи"""
        original_users: list[dict[str, str]] = [
            {"username": "alice"},
        ]

        self.db.write_json("users_file", original_users)

        with patch(
            "valutatrade_hub.infra.database.os.replace",
            side_effect=OSError("Ошибка диска"),
        ):
            with self.assertRaises(OSError):
                self.db.write_json(
                    "users_file",
                    [{"username": "bob"}],
                )

        restored = self.db.read_json("users_file", [])

        self.assertEqual(restored, original_users)


if __name__ == "__main__":
    unittest.main()