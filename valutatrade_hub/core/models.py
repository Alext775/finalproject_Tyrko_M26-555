"""Модели пользователя, кошелька и портфеля"""

import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import datetime
from typing import Any, Self

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import InsufficientFundsError
from valutatrade_hub.core.utils import (
    MIN_PASSWORD_LENGTH,
    parse_utc_iso,
    to_utc_iso,
    utc_now,
    validate_nonnegative_number,
    validate_positive_amount,
)


def _validate_user_id(value: object) -> int:
    """Проверить идентификатор пользователя"""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("user_id должен быть положительным целым числом")

    return value


def _validate_nonempty_string(value: object, field_name: str) -> str:
    """Проверить непустую строку"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} не может быть пустым")

    return value.strip()


def _validate_password(password: object) -> str:
    """Проверить длину и тип пароля"""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов")

    return password


def _validate_registration_date(value: object) -> datetime:
    """Проверить дату регистрации"""
    if not isinstance(value, datetime):
        raise ValueError("Некорректная дата регистрации")

    return value


def _hash_password(password: str, salt: str) -> str:
    """Получить хеш пароля с солью"""
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


def _verify_password(
    password: object,
    salt: str,
    hashed_password: str,
) -> bool:
    """Проверить соответствие пароля хешу"""
    if not isinstance(password, str):
        return False

    candidate = _hash_password(password, salt)
    return hmac.compare_digest(candidate, hashed_password)


class User:
    """Пользователь системы"""

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ):
        self._user_id = _validate_user_id(user_id)
        self._username = _validate_nonempty_string(username, "Имя пользователя")
        self._hashed_password = _validate_nonempty_string(hashed_password, "Хеш пароля")
        self._salt = _validate_nonempty_string(salt, "Соль")
        self._registration_date = _validate_registration_date(registration_date)

    @classmethod
    def create(cls, user_id: int, username: str, password: str) -> Self:
        """Создать пользователя с уникальной солью"""
        validated_password = _validate_password(password)
        salt = secrets.token_hex(16)
        hashed_password = _hash_password(validated_password, salt)

        return cls(
            user_id,
            username,
            hashed_password,
            salt,
            utc_now(),
        )

    @property
    def user_id(self) -> int:
        """Получить ID"""
        return self._user_id

    @property
    def username(self) -> str:
        """Получить имя"""
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        self._username = _validate_nonempty_string(value, "Имя пользователя")

    @property
    def hashed_password(self) -> str:
        """Получить хеш для сохранения"""
        return self._hashed_password

    @property
    def salt(self) -> str:
        """Получить соль"""
        return self._salt

    @property
    def registration_date(self) -> datetime:
        """Получить дату регистрации"""
        return self._registration_date

    def get_user_info(self) -> dict[str, int | str]:
        """Получить информацию без пароля"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "registration_date": to_utc_iso(self.registration_date),
        }

    def change_password(self, new_password: str) -> None:
        """Изменить пароль с хешированием"""
        validated_password = _validate_password(new_password)
        self._hashed_password = _hash_password(validated_password, self._salt)

    def verify_password(self, password: str) -> bool:
        """Проверить пароль"""
        return _verify_password(
            password,
            self._salt,
            self._hashed_password,
        )

    def to_dict(self) -> dict[str, int | str]:
        """Подготовить запись для JSON"""
        return {
            **self.get_user_info(),
            "hashed_password": self.hashed_password,
            "salt": self.salt,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> Self:
        """Загрузить пользователя из JSON"""
        return cls(
            row["user_id"],
            row["username"],
            row["hashed_password"],
            row["salt"],
            parse_utc_iso(row["registration_date"]),
        )


class Wallet:
    """Кошелек одной валюты"""

    def __init__(
        self,
        currency_code: str,
        balance: float = 0.0,
    ):
        self.currency_code = get_currency(currency_code).code
        self.balance = balance

    @property
    def balance(self) -> float:
        """Получить баланс"""
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        self._balance = validate_nonnegative_number(value)

    def deposit(self, amount: float) -> None:
        """Пополнить баланс"""
        self.balance += validate_positive_amount(amount)

    def withdraw(self, amount: float) -> None:
        """Снять средства"""
        amount = validate_positive_amount(amount)

        if amount > self.balance:
            raise InsufficientFundsError(
                self.balance,
                amount,
                self.currency_code,
            )

        self.balance -= amount

    def get_balance_info(self) -> str:
        """Получить строку баланса"""
        return f"{self.currency_code}: {self.balance:.4f}"

    def to_dict(self) -> dict[str, str | float]:
        """Подготовить JSON-представление"""
        return {
            "currency_code": self.currency_code,
            "balance": self.balance,
        }


DEMO_USD_RATES: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.30,
    "RUB": 0.011,
    "BTC": 59000.0,
    "ETH": 3700.0,
    "SOL": 145.0,
}


def _validate_user(value: object) -> User:
    """Проверить объект пользователя"""
    if not isinstance(value, User):
        raise TypeError("Портфелю требуется объект User")

    return value


def _validate_wallet(code: str, value: object) -> Wallet:
    """Проверить кошелек и соответствие кода валюты"""
    if not isinstance(value, Wallet) or value.currency_code != code:
        raise ValueError("Ключ и валюта кошелька должны совпадать")

    return value


class Portfolio:
    """Портфель пользователя"""

    def __init__(
        self,
        user: User,
        wallets: dict[str, Wallet] | None = None,
    ):
        self._user = _validate_user(user)
        self._user_id = self._user.user_id
        self._wallets: dict[str, Wallet] = {}

        for code, wallet in (wallets or {}).items():
            self._wallets[code] = _validate_wallet(code, wallet)

    @property
    def user(self) -> User:
        """Получить пользователя"""
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Получить копию словаря кошельков"""
        return self._wallets.copy()

    def add_currency(self, currency_code: str) -> Wallet:
        """Добавить валюту, если кошелька еще нет"""
        get_currency(currency_code)

        if currency_code not in self._wallets:
            self._wallets[currency_code] = Wallet(currency_code)

        return self._wallets[currency_code]

    def get_wallet(self, currency_code: str) -> Wallet | None:
        """Найти кошелек"""
        get_currency(currency_code)
        return self._wallets.get(currency_code)

    def get_total_value(
        self,
        base_currency: str = "USD",
        rate_provider: Callable[[str, str], float] | None = None,
    ) -> float:
        """Посчитать общую стоимость портфеля"""
        get_currency(base_currency)

        def demo_rate(from_code: str, to_code: str) -> float:
            """Получить учебный обменный курс"""
            return DEMO_USD_RATES[from_code] / DEMO_USD_RATES[to_code]

        provider = rate_provider if rate_provider is not None else demo_rate

        return sum(
            wallet.balance * provider(code, base_currency)
            for code, wallet in self._wallets.items()
            if wallet.balance > 0
        )

    def to_dict(self) -> dict[str, Any]:
        """Преобразовать портфель в JSON"""
        return {
            "user_id": self._user_id,
            "wallets": {
                code: wallet.to_dict() for code, wallet in self._wallets.items()
            },
        }

    @classmethod
    def from_dict(cls, user: User, row: dict[str, Any]) -> Self:
        """Загрузить портфель из JSON"""
        if row["user_id"] != user.user_id:
            raise ValueError("Портфель принадлежит другому пользователю")

        wallets = {
            code: Wallet(code, data["balance"])
            for code, data in row.get("wallets", {}).items()
        }

        return cls(user, wallets)
