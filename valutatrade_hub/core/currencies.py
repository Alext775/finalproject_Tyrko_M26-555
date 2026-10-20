"""Иерархия валют и реестр"""

import math
from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError
from valutatrade_hub.core.utils import validate_currency_code


def _validate_nonempty_string(value: object, field_name: str) -> str:
    """Проверить непустую строку"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} не может быть пустым")

    return value.strip()


def _validate_market_cap(value: object) -> float:
    """Проверить рыночную капитализацию"""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("Капитализация не может быть отрицательной")

    return float(value)


class Currency(ABC):
    """Абстрактный базовый класс валюты"""

    def __init__(self, name: str, code: str):
        self.name = _validate_nonempty_string(name, "Имя валюты")
        self.code = validate_currency_code(code)

    @abstractmethod
    def get_display_info(self) -> str:
        """Получить информацию о валюте"""


class FiatCurrency(Currency):
    """Фиатная валюта"""

    def __init__(
        self,
        name: str,
        code: str,
        issuing_country: str,
    ):
        super().__init__(name, code)
        self.issuing_country = _validate_nonempty_string(
            issuing_country, "Страна эмиссии"
        )

    def get_display_info(self) -> str:
        """Информация о фиатной валюте"""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Криптовалюта"""

    def __init__(
        self,
        name: str,
        code: str,
        algorithm: str,
        market_cap: float,
    ):
        super().__init__(name, code)
        self.algorithm = _validate_nonempty_string(algorithm, "Алгоритм")
        self.market_cap = _validate_market_cap(market_cap)

    def get_display_info(self) -> str:
        """Информация о криптовалюте"""
        cap = format(self.market_cap, ".2e").replace("e+", "e")

        return (
            f"[CRYPTO] {self.code} — {self.name} (Algo: {self.algorithm}, MCAP: {cap})"
        )


CURRENCY_REGISTRY: dict[str, Currency] = {
    "USD": FiatCurrency("US Dollar", "USD", "United States"),
    "EUR": FiatCurrency("Euro", "EUR", "Eurozone"),
    "GBP": FiatCurrency("British Pound", "GBP", "United Kingdom"),
    "RUB": FiatCurrency("Russian Ruble", "RUB", "Russia"),
    "BTC": CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
    "ETH": CryptoCurrency("Ethereum", "ETH", "Proof of Stake", 4.2e11),
    "SOL": CryptoCurrency("Solana", "SOL", "Proof of History", 7.0e10),
}


def get_currency(code: str) -> Currency:
    """Получить объект валюты по коду"""
    validate_currency_code(code)

    try:
        return CURRENCY_REGISTRY[code]
    except KeyError as exc:
        raise CurrencyNotFoundError(code) from exc
