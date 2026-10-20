"""Клиенты CoinGecko и ExchangeRate-API"""

import math
from abc import ABC, abstractmethod

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import ParserConfig


def _network_error(
    provider: str,
    exc: requests.RequestException,
    response: object,
) -> ApiRequestError:
    """Подготовить сообщение о сетевой ошибке"""
    status = getattr(response, "status_code", None)

    if status == 429:
        reason = "лимит запросов (429), повторите позже"
    elif status in (401, 403):
        reason = (
            f"авторизация запрещена (HTTP {status}), "
            "проверьте ключ"
        )
    elif status is not None:
        reason = f"HTTP {status}"
    else:
        reason = f"ошибка сети ({type(exc).__name__})"

    return ApiRequestError(f"{provider}: {reason}")


def _positive_rate(value: object, code: str) -> float:
    """Проверить полученный курс"""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ApiRequestError(
            f"Некорректный курс {code}: {value!r}"
        )

    return float(value)


class BaseApiClient(ABC):
    """Общий интерфейс API-клиентов"""

    source: str

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Получить словарь курсов валют"""


class CoinGeckoClient(BaseApiClient):
    """Получение криптовалют через CoinGecko"""

    source = "CoinGecko"

    def __init__(
        self,
        config: ParserConfig | None = None,
    ) -> None:
        self.config = config or ParserConfig()

    def fetch_rates(self) -> dict[str, float]:
        """Получить курсы BTC, ETH, SOL"""
        config = self.config

        ids = [
            config.crypto_id_map[code]
            for code in config.crypto_currencies
        ]

        response = None

        try:
            response = requests.get(
                config.coingecko_url,
                params={
                    "ids": ",".join(ids),
                    "vs_currencies": "usd",
                },
                timeout=config.request_timeout,
            )

            response.raise_for_status()
            payload = response.json()

        except requests.RequestException as exc:
            raise _network_error(
                "CoinGecko",
                exc,
                response,
            ) from exc

        except ValueError as exc:
            raise ApiRequestError(
                "CoinGecko: некорректный JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise ApiRequestError(
                "CoinGecko: неверный формат JSON"
            )

        rates = {}

        for code in config.crypto_currencies:
            raw_id = config.crypto_id_map[code]
            item = payload.get(raw_id)

            if not isinstance(item, dict) or "usd" not in item:
                raise ApiRequestError(
                    f"CoinGecko: отсутствует курс {code}"
                )

            rates[f"{code}_USD"] = _positive_rate(
                item["usd"],
                code,
            )

        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Получение фиатных курсов"""

    source = "ExchangeRate-API"

    def __init__(
        self,
        config: ParserConfig | None = None,
    ) -> None:
        self.config = config or ParserConfig()

    def fetch_rates(self) -> dict[str, float]:
        """Получить курсы EUR, GBP, RUB к USD"""
        config = self.config

        if not config.exchangerate_api_key:
            raise ApiRequestError(
                "Не задан EXCHANGERATE_API_KEY"
            )

        url = (
            f"{config.exchangerate_api_url}/"
            f"{config.exchangerate_api_key}/"
            f"latest/{config.base_currency}"
        )

        response = None

        try:
            response = requests.get(
                url,
                timeout=config.request_timeout,
            )

            response.raise_for_status()
            payload = response.json()

        except requests.RequestException as exc:
            raise _network_error(
                "ExchangeRate-API",
                exc,
                response,
            ) from exc

        except ValueError as exc:
            raise ApiRequestError(
                "ExchangeRate-API: некорректный JSON"
            ) from exc

        if (
            not isinstance(payload, dict)
            or payload.get("result") != "success"
        ):
            reason = (
                payload.get("error-type", "неверный ответ")
                if isinstance(payload, dict)
                else "неверный формат JSON"
            )

            raise ApiRequestError(
                f"ExchangeRate-API: {reason}"
            )

        conversion_rates = payload.get("conversion_rates")

        if not isinstance(conversion_rates, dict):
            raise ApiRequestError(
                "ExchangeRate-API: отсутствует conversion_rates"
            )

        rates = {}

        for code in config.fiat_currencies:
            usd_to_code = _positive_rate(
                conversion_rates.get(code),
                code,
            )

            # API возвращает USD -> EUR.
            # Нам нужен обратный курс EUR -> USD.
            rates[
                f"{code}_{config.base_currency}"
            ] = 1.0 / usd_to_code

        return rates