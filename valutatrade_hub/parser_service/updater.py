"""Сервис обновления курсов валют"""

import logging
from typing import Self, TypedDict

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import to_utc_iso
from valutatrade_hub.parser_service.api_clients import (
    BaseApiClient,
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RateEntry, RatesStorage

SOURCE_NAMES = {
    "coingecko": "CoinGecko",
    "exchangerate": "ExchangeRate-API",
}


class UpdateResult(TypedDict):
    """Результат обновления курсов"""

    updated: int
    failures: dict[str, str]
    last_refresh: str


class RatesUpdater:
    """Обновление данных из нескольких API"""

    def __init__(
        self,
        clients: list[BaseApiClient],
        storage: RatesStorage,
    ) -> None:
        self.clients = clients
        self.storage = storage
        self.logger = logging.getLogger("valutatrade.parser")

    @classmethod
    def create_default(cls) -> Self:
        """Создать обновлятор с двумя источниками"""
        config = ParserConfig()

        return cls(
            [
                CoinGeckoClient(config),
                ExchangeRateApiClient(config),
            ],
            RatesStorage(),
        )

    def run_update(
        self,
        source: str | None = None,
    ) -> UpdateResult:
        """Загрузить новые курсы и сохранить их"""
        if source is not None and source not in SOURCE_NAMES:
            raise ValueError("Источник: coingecko или exchangerate")

        if source is None:
            selected = self.clients
        else:
            source_name = SOURCE_NAMES[source]
            selected = [
                client for client in self.clients if client.source == source_name
            ]

        if not selected:
            raise ValueError("Не найден выбранный источник")

        updates: dict[str, RateEntry] = {}
        failures: dict[str, str] = {}

        self.logger.info("Начало обновления курсов")

        for client in selected:
            try:
                rates = client.fetch_rates()

                if not rates:
                    raise ApiRequestError("Сервис вернул пустой набор курсов")

                received_at = to_utc_iso()

                for pair, rate in rates.items():
                    updates[pair] = {
                        "rate": rate,
                        "updated_at": received_at,
                        "source": client.source,
                    }

                self.logger.info(
                    "%s: OK (%s курсов)",
                    client.source,
                    len(rates),
                )

            except ApiRequestError as exc:
                failures[client.source] = str(exc)

                self.logger.error(
                    "%s: ERROR %s",
                    client.source,
                    exc,
                )

        if not updates:
            details = "; ".join(failures.values())

            raise ApiRequestError(f"Все источники недоступны: {details}")

        timestamp = to_utc_iso()

        saved = self.storage.save_rates(
            updates,
            timestamp,
        )

        self.logger.info(
            "Завершено: сохранено %s, ошибок %s",
            saved,
            len(failures),
        )

        return {
            "updated": saved,
            "failures": failures,
            "last_refresh": timestamp,
        }
