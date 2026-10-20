"""Клиенты CoinGecko и ExchangeRate-API"""

from abc import ABC, abstractmethod
from typing import cast

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import validate_positive_amount
from valutatrade_hub.parser_service.config import ParserConfig


def _network_error(
    provider: str,
    exc: requests.RequestException,
    response: requests.Response | None,
) -> ApiRequestError:
    """Подготовить сообщение о сетевой ошибке"""
    status = response.status_code if response is not None else None

    if status == 429:
        reason = "лимит запросов (429), повторите позже"

    elif status in (401, 403):
        reason = f"авторизация запрещена (HTTP {status}), проверьте ключ"

    elif status is not None:
        reason = f"HTTP {status}"

    else:
        reason = f"ошибка сети ({type(exc).__name__})"

    return ApiRequestError(f"{provider}: {reason}")


def _positive_rate(value: object, code: str) -> float:
    """Проверить полученный курс"""
    try:
        return validate_positive_amount(value)

    except ValueError as exc:
        raise ApiRequestError(f"Некорректный курс {code}: {value!r}") from exc


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
        self.config = config if config is not None else ParserConfig()

    def fetch_rates(self) -> dict[str, float]:
        """Получить курсы криптовалют"""
        config = self.config

        crypto_ids = [config.crypto_id_map[code] for code in config.crypto_currencies]

        response: requests.Response | None = None

        try:
            response = requests.get(
                config.coingecko_url,
                params={
                    "ids": ",".join(crypto_ids),
                    "vs_currencies": "usd",
                },
                timeout=config.request_timeout,
            )

            response.raise_for_status()
            payload: object = response.json()

        except requests.RequestException as exc:
            raise _network_error(
                self.source,
                exc,
                response,
            ) from exc

        except ValueError as exc:
            raise ApiRequestError("CoinGecko: некорректный JSON") from exc

        if not isinstance(payload, dict):
            raise ApiRequestError("CoinGecko: неверный формат JSON")

        data = cast(dict[str, object], payload)
        rates: dict[str, float] = {}

        for code in config.crypto_currencies:
            raw_id = config.crypto_id_map[code]
            item = data.get(raw_id)

            if not isinstance(item, dict):
                raise ApiRequestError(f"CoinGecko: отсутствует курс {code}")

            currency_data = cast(dict[str, object], item)

            if "usd" not in currency_data:
                raise ApiRequestError(f"CoinGecko: отсутствует курс {code}")

            rates[f"{code}_USD"] = _positive_rate(
                currency_data["usd"],
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
        self.config = config if config is not None else ParserConfig()

    def fetch_rates(self) -> dict[str, float]:
        """Получить курсы фиатных валют к базовой валюте"""
        config = self.config

        if not config.exchangerate_api_key:
            raise ApiRequestError("Не задан EXCHANGERATE_API_KEY")

        url = (
            f"{config.exchangerate_api_url}/"
            f"{config.exchangerate_api_key}/"
            f"latest/{config.base_currency}"
        )

        response: requests.Response | None = None

        try:
            response = requests.get(
                url,
                timeout=config.request_timeout,
            )

            response.raise_for_status()
            payload: object = response.json()

        except requests.RequestException as exc:
            raise _network_error(
                self.source,
                exc,
                response,
            ) from exc

        except ValueError as exc:
            raise ApiRequestError("ExchangeRate-API: некорректный JSON") from exc

        if not isinstance(payload, dict):
            raise ApiRequestError("ExchangeRate-API: неверный формат JSON")

        data = cast(dict[str, object], payload)

        if data.get("result") != "success":
            reason = data.get("error-type", "неверный ответ")
            raise ApiRequestError(f"ExchangeRate-API: {reason}")

        raw_rates = data.get("conversion_rates")

        if not isinstance(raw_rates, dict):
            raise ApiRequestError("ExchangeRate-API: отсутствует conversion_rates")

        conversion_rates = cast(dict[str, object], raw_rates)
        rates: dict[str, float] = {}

        for code in config.fiat_currencies:
            base_to_currency = _positive_rate(
                conversion_rates.get(code),
                code,
            )

            # API возвращает курс базовой валюты к указанной
            # Для хранения нужен обратный курс к базовой валюте
            rates[f"{code}_{config.base_currency}"] = 1.0 / base_to_currency

        return rates
