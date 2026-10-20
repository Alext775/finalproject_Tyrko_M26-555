"""Модели пользователя, кошелька и портфеля"""

import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Callable

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
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id должен быть положительным целым числом")

        self._user_id = user_id
        self.username = username

        if not isinstance(hashed_password, str) or not hashed_password:
            raise ValueError("Хеш пароля не может быть пустым")
        if not isinstance(salt, str) or not salt:
            raise ValueError("Соль не может быть пустой")
        if not isinstance(registration_date, datetime):
            raise ValueError("Некорректная дата регистрации")

        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @classmethod
    def create(cls, user_id: int, username: str, password: str) -> "User":
        """Создать пользователя с уникальной солью"""
        user = cls(
            user_id,
            username,
            "pending",
            secrets.token_hex(16),
            utc_now(),
        )
        user.change_password(password)
        return user

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
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value.strip()

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

    def get_user_info(self) -> dict:
        """Информация без пароля"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "registration_date": to_utc_iso(self.registration_date),
        }

    def change_password(self, new_password: str) -> None:
        """Изменить пароль с хешированием"""
        if (
            not isinstance(new_password, str)
            or len(new_password) < MIN_PASSWORD_LENGTH
        ):
            raise ValueError(
                f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов"
            )

        self._hashed_password = hashlib.sha256(
            (new_password + self._salt).encode("utf-8")
        ).hexdigest()

    def verify_password(self, password: str) -> bool:
        """Проверить пароль"""
        if not isinstance(password, str):
            return False

        candidate = hashlib.sha256(
            (password + self._salt).encode("utf-8")
        ).hexdigest()

        return hmac.compare_digest(candidate, self._hashed_password)

    def to_dict(self) -> dict:
        """Подготовить запись для JSON"""
        return {
            **self.get_user_info(),
            "hashed_password": self.hashed_password,
            "salt": self.salt,
        }

    @classmethod
    def from_dict(cls, row: dict) -> "User":
        """Загрузить пользователя из JSON"""
        return cls(
            row["user_id"],
            row["username"],
            row["hashed_password"],
            row["salt"],
            parse_utc_iso(row["registration_date"]),
        )


class Wallet:
    """Кошелёк одной валюты"""

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

    def to_dict(self) -> dict:
        """Подготовить JSON-представление"""
        return {
            "currency_code": self.currency_code,
            "balance": self.balance,
        }


# Фиксированные курсы для проверки модели.
DEMO_USD_RATES = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.30,
    "RUB": 0.011,
    "BTC": 59000.0,
    "ETH": 3700.0,
    "SOL": 145.0,
}


class Portfolio:
    """Портфель пользователя"""

    def __init__(
        self,
        user: User,
        wallets: dict[str, Wallet] | None = None,
    ):
        if not isinstance(user, User):
            raise TypeError("Портфелю требуется объект User")

        self._user = user
        self._user_id = user.user_id
        self._wallets: dict[str, Wallet] = {}

        for code, wallet in (wallets or {}).items():
            if not isinstance(wallet, Wallet) or wallet.currency_code != code:
                raise ValueError("Ключ и валюта кошелька должны совпадать")

            self._wallets[code] = wallet

    @property
    def user(self) -> User:
        """Получить пользователя"""
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Получить копию словаря кошельков"""
        return self._wallets.copy()

    def add_currency(self, currency_code: str) -> Wallet:
        """Добавить валюту, если кошелька ещё нет"""
        get_currency(currency_code)

        if currency_code not in self._wallets:
            self._wallets[currency_code] = Wallet(currency_code)

        return self._wallets[currency_code]

    def get_wallet(self, currency_code: str) -> Wallet | None:
        """Найти кошелёк"""
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
            return DEMO_USD_RATES[from_code] / DEMO_USD_RATES[to_code]

        provider = rate_provider or demo_rate

        return sum(
            wallet.balance * provider(code, base_currency)
            for code, wallet in self._wallets.items()
            if wallet.balance
        )

    def to_dict(self) -> dict:
        """Преобразовать портфель в JSON"""
        return {
            "user_id": self._user_id,
            "wallets": {
                code: wallet.to_dict()
                for code, wallet in self._wallets.items()
            },
        }

    @classmethod
    def from_dict(cls, user: User, row: dict) -> "Portfolio":
        """Загрузить портфель из JSON"""
        if row["user_id"] != user.user_id:
            raise ValueError("Портфель принадлежит другому пользователю")

        wallets = {
            code: Wallet(code, data["balance"])
            for code, data in row.get("wallets", {}).items()
        }

        return cls(user, wallets)