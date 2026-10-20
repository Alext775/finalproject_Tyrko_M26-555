"""Общие функции проверки данных"""

import math
import re
from datetime import datetime, timezone

CURRENCY_PATTERN = re.compile(r"^[A-Z]{2,5}$")
MIN_PASSWORD_LENGTH = 4
CACHE_CLOCK_SKEW_SECONDS = 60


def validate_currency_code(code: str) -> str:
    """Проверить формат валютного кода"""
    if not isinstance(code, str) or not CURRENCY_PATTERN.fullmatch(code):
        raise ValueError(
            "Код валюты должен содержать 2–5 заглавных латинских букв"
        )
    return code


def validate_positive_amount(amount: float) -> float:
    """Проверить положительную сумму."""
    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not math.isfinite(amount)
        or amount <= 0
    ):
        raise ValueError("'amount' должен быть положительным числом")

    return float(amount)


def validate_nonnegative_number(value: float) -> float:
    """Проверить неотрицательный баланс"""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(
            "Баланс должен быть неотрицательным конечным числом"
        )

    return float(value)


def utc_now() -> datetime:
    """Получить текущее UTC-время"""
    return datetime.now(timezone.utc)


def to_utc_iso(value: datetime | None = None) -> str:
    """Преобразовать время в строку ISO UTC."""
    value = value or utc_now()

    return (
        value.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_utc_iso(value: str) -> datetime:
    """Преобразовать строку ISO в datetime"""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)