
"""Тесты постоянного хранения API-ключей"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from valutatrade_hub.parser_service import credentials


class CredentialsTests(unittest.TestCase):
    """Проверки сохранения и замены API-ключа"""

    def setUp(self) -> None:
        """Создать временное хранилище ключей"""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        directory = Path(self.temp.name)
        credentials_file = directory / "credentials.json"

        directory_patch = patch.object(
            credentials,
            "CREDENTIALS_DIR",
            directory,
        )
        file_patch = patch.object(
            credentials,
            "CREDENTIALS_FILE",
            credentials_file,
        )
        environment_patch = patch.dict(
            os.environ,
            {"EXCHANGERATE_API_KEY": ""},
        )

        directory_patch.start()
        file_patch.start()
        environment_patch.start()

        self.addCleanup(environment_patch.stop)
        self.addCleanup(file_patch.stop)
        self.addCleanup(directory_patch.stop)

    def test_save_and_load(self) -> None:
        """Проверить сохранение и повторную загрузку ключа"""
        credentials.save_api_key("test-key")

        self.assertEqual(
            credentials.load_api_key(),
            "test-key",
        )

    def test_skip_existing_key(self) -> None:
        """Проверить сохранение старого ключа при пропуске"""
        credentials.save_api_key("old-key")

        with patch.object(credentials, "getpass", return_value=""):
            result = credentials.configure_api_key(force=True)

        self.assertTrue(result)
        self.assertEqual(
            credentials.load_api_key(),
            "old-key",
        )

    def test_replace_key(self) -> None:
        """Проверить замену сохраненного ключа"""
        credentials.save_api_key("old-key")

        with patch.object(
            credentials,
            "getpass",
            return_value="new-key",
        ):
            result = credentials.configure_api_key(force=True)

        self.assertTrue(result)
        self.assertEqual(
            credentials.load_api_key(),
            "new-key",
        )

    def test_skip_without_key(self) -> None:
        """Проверить пропуск ввода при отсутствии ключа"""
        with patch.object(credentials, "getpass", return_value=""):
            result = credentials.configure_api_key()

        self.assertFalse(result)
        self.assertIsNone(credentials.load_api_key())

    def test_invalid_key(self) -> None:
        """Проверить запрет пустого ключа и пробелов"""
        with self.assertRaises(ValueError):
            credentials.save_api_key("")

        with self.assertRaises(ValueError):
            credentials.save_api_key("invalid key")


if __name__ == "__main__":
    unittest.main()