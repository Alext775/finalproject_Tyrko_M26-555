"""Иерархия валют и реестр"""

import math
from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError
from valutatrade_hub.core.utils import validate_currency_code


class Currency(ABC):
    """Абстрактный базовый класс валюты"""

    def __init__(self, name: str, code: str):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Имя валюты не может быть пустым")

        self.name = name.strip()
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

        if not isinstance(issuing_country, str) or not issuing_country.strip():
            raise ValueError("Страна эмиссии не может быть пустой")

        self.issuing_country = issuing_country.strip()

    def get_display_info(self) -> str:
        """Информация о фиатной валюте"""
        return (
            f"[FIAT] {self.code} — {self.name} "
            f"(Issuing: {self.issuing_country})"
        )


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

        if not isinstance(algorithm, str) or not algorithm.strip():
            raise ValueError("Алгоритм не может быть пустым")

        if (
            isinstance(market_cap, bool)
            or not isinstance(market_cap, (int, float))
            or not math.isfinite(market_cap)
            or market_cap < 0
        ):
            raise ValueError("Капитализация не может быть отрицательной")

        self.algorithm = algorithm.strip()
        self.market_cap = float(market_cap)

    def get_display_info(self) -> str:
        """Информация о криптовалюте"""
        cap = format(self.market_cap, ".2e").replace("e+", "e")

        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {cap})"
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