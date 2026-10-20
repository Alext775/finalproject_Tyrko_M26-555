"""Конфигурация сервиса получения курсов"""

from dataclasses import dataclass, field
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.credentials import load_api_key

CRYPTO_ID_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
}

FIAT_CURRENCIES = ("EUR", "GBP", "RUB")
CRYPTO_CURRENCIES = tuple(CRYPTO_ID_MAP)

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
EXCHANGERATE_API_URL = "https://v6.exchangerate-api.com/v6"

REQUEST_TIMEOUT = 10


@dataclass(frozen=True)
class ParserConfig:
    """Параметры API и хранения курсов"""

    exchangerate_api_key: str | None = field(default_factory=load_api_key)

    coingecko_url: str = COINGECKO_URL
    exchangerate_api_url: str = EXCHANGERATE_API_URL

    base_currency: str = "USD"

    fiat_currencies: tuple[str, ...] = FIAT_CURRENCIES
    crypto_currencies: tuple[str, ...] = CRYPTO_CURRENCIES

    crypto_id_map: dict[str, str] = field(default_factory=lambda: CRYPTO_ID_MAP.copy())

    request_timeout: int = REQUEST_TIMEOUT

    rates_file_path: Path = field(
        default_factory=lambda: SettingsLoader().get("rates_file")
    )

    history_file_path: Path = field(
        default_factory=lambda: SettingsLoader().get("history_file")
    )
