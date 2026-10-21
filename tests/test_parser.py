"""Тесты API-клиентов и сервиса обновления"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.api_clients import (
    BaseApiClient,
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import (
    HistoryEntry,
    RateSnapshot,
    RatesStorage,
)
from valutatrade_hub.parser_service.updater import RatesUpdater


class ApiClientTests(unittest.TestCase):
    """Проверки с заменой сетевых запросов"""

    @patch("valutatrade_hub.parser_service.api_clients.requests.get")
    def test_fiat_rates(self, get: Mock) -> None:
        """Проверить получение фиатных курсов"""
        response = get.return_value

        response.json.return_value = {
            "result": "success",
            "conversion_rates": {
                "EUR": 0.8,
                "GBP": 0.5,
                "RUB": 100,
            },
        }

        config = ParserConfig(exchangerate_api_key="fake-key")

        rates = ExchangeRateApiClient(config).fetch_rates()

        self.assertAlmostEqual(rates["EUR_USD"], 1.25)
        self.assertAlmostEqual(rates["GBP_USD"], 2)
        self.assertAlmostEqual(rates["RUB_USD"], 0.01)

    @patch("valutatrade_hub.parser_service.api_clients.requests.get")
    def test_coingecko(self, get: Mock) -> None:
        """Проверить получение криптовалютных курсов"""
        get.return_value.json.return_value = {
            "bitcoin": {"usd": 60000},
            "ethereum": {"usd": 3000},
            "solana": {"usd": 100},
        }

        result = CoinGeckoClient().fetch_rates()

        self.assertEqual(result["BTC_USD"], 60000)

    @patch("valutatrade_hub.parser_service.api_clients.requests.get")
    def test_rate_limit(self, get: Mock) -> None:
        """Проверить обработку ограничения запросов"""
        get.return_value.status_code = 429

        get.return_value.raise_for_status.side_effect = requests.HTTPError()

        with self.assertRaisesRegex(ApiRequestError, "429"):
            CoinGeckoClient().fetch_rates()

    @patch("valutatrade_hub.parser_service.api_clients.requests.get")
    def test_network_error(self, get: Mock) -> None:
        """Проверить обработку сетевой ошибки"""
        get.side_effect = requests.Timeout("timeout")

        with self.assertRaises(ApiRequestError):
            CoinGeckoClient().fetch_rates()


class FakeClient(BaseApiClient):
    """Тестовый источник курсов"""

    def __init__(
        self,
        source: str,
        rates: dict[str, float] | None = None,
    ) -> None:
        self.source = source
        self.rates = rates

    def fetch_rates(self) -> dict[str, float]:
        """Получить тестовые курсы"""
        if self.rates is None:
            raise ApiRequestError("Тестовый сбой")

        return self.rates


class UpdaterTests(unittest.TestCase):
    """Проверки отказоустойчивости и истории"""

    def setUp(self) -> None:
        """Подготовить временное хранилище"""
        self.temp = tempfile.TemporaryDirectory()

        self.env_patch = patch.dict(
            os.environ,
            {"VALUTATRADE_DATA_DIR": self.temp.name},
        )

        self.env_patch.start()
        SettingsLoader().reload()

    def tearDown(self) -> None:
        """Восстановить настройки после теста"""
        self.env_patch.stop()
        SettingsLoader().reload()
        self.temp.cleanup()

    def test_partial_failure_and_history(self) -> None:
        """Проверить частичный сбой и сохранение истории"""
        updater = RatesUpdater(
            [
                FakeClient(
                    "CoinGecko",
                    {"BTC_USD": 60000.0},
                ),
                FakeClient("ExchangeRate-API"),
            ],
            RatesStorage(),
        )

        result = updater.run_update()

        self.assertEqual(result["updated"], 1)
        self.assertIn(
            "ExchangeRate-API",
            result["failures"],
        )

        data_dir = Path(self.temp.name)

        snapshot = cast(
            RateSnapshot,
            json.loads((data_dir / "rates.json").read_text(encoding="utf-8")),
        )

        history = cast(
            list[HistoryEntry],
            json.loads((data_dir / "exchange_rates.json").read_text(encoding="utf-8")),
        )

        self.assertEqual(
            snapshot["pairs"]["BTC_USD"]["rate"],
            60000.0,
        )

        self.assertEqual(len(history), 1)

        self.assertTrue(history[0]["id"].startswith("BTC_USD_"))

        RatesStorage().save_rates(
            {"BTC_USD": snapshot["pairs"]["BTC_USD"]},
            result["last_refresh"],
        )

        history = cast(
            list[HistoryEntry],
            json.loads((data_dir / "exchange_rates.json").read_text(encoding="utf-8")),
        )

        self.assertEqual(len(history), 1)

    def test_all_fail(self) -> None:
        """Проверить сбой всех источников"""
        updater = RatesUpdater(
            [FakeClient("CoinGecko")],
            RatesStorage(),
        )

        with self.assertRaises(ApiRequestError):
            updater.run_update()


if __name__ == "__main__":
    unittest.main()
