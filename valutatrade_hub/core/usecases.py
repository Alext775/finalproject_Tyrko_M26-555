"""Бизнес-логика валютного кошелька"""

from typing import Any, TypedDict

from valutatrade_hub.core.currencies import CryptoCurrency, get_currency
from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.core.utils import (
    CACHE_CLOCK_SKEW_SECONDS,
    parse_utc_iso,
    to_utc_iso,
    utc_now,
    validate_positive_amount,
)
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader

USD_CODE = "USD"
JsonObject = dict[str, Any]


class RateQuote(TypedDict):
    """Курс и информация о времени обновления"""

    rate: float
    updated_at: str
    source: str


RateResult = TypedDict(
    "RateResult",
    {
        "from": str,
        "to": str,
        "rate": float,
        "updated_at": str,
        "source": str,
    },
)


def _validate_username(value: object) -> str:
    """Проверить непустое имя пользователя"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Имя пользователя не может быть пустым")

    return value.strip()


class UseCases:
    """Основные операции приложения"""

    def __init__(
        self,
        db: DatabaseManager | None = None,
        settings: SettingsLoader | None = None,
    ) -> None:
        self.db = db if db is not None else DatabaseManager()
        self.settings = settings if settings is not None else SettingsLoader()

    def register(self, username: str, password: str) -> dict[str, int | str]:
        """Зарегистрировать пользователя"""
        username = _validate_username(username)

        with self.db.transaction_lock:
            rows: list[JsonObject] = self.db.read_json("users_file", [])

            if any(row["username"] == username for row in rows):
                raise ValueError(f"Имя пользователя '{username}' уже занято")

            new_id = max((row["user_id"] for row in rows), default=0) + 1
            user = User.create(new_id, username, password)

            portfolios: list[JsonObject] = self.db.read_json("portfolios_file", [])
            portfolios.append(Portfolio(user).to_dict())
            rows.append(user.to_dict())

            self.db.write_json("portfolios_file", portfolios)
            self.db.write_json("users_file", rows)

        return user.get_user_info()

    def login(self, username: str, password: str) -> dict[str, int | str]:
        """Авторизовать пользователя"""
        username = _validate_username(username)
        rows: list[JsonObject] = self.db.read_json("users_file", [])

        row = next(
            (item for item in rows if item["username"] == username),
            None,
        )

        if row is None:
            raise ValueError(f"Пользователь '{username}' не найден")

        user = User.from_dict(row)

        if not user.verify_password(password):
            raise ValueError("Неверный пароль")

        return user.get_user_info()

    def _user_by_id(self, user_id: int) -> User:
        """Найти пользователя по ID"""
        rows: list[JsonObject] = self.db.read_json("users_file", [])

        for row in rows:
            if row["user_id"] == user_id:
                return User.from_dict(row)

        raise ValueError("Пользователь не найден. Выполните login")

    @staticmethod
    def _portfolio(user: User, rows: list[JsonObject]) -> Portfolio:
        """Получить портфель пользователя"""
        row = next(
            (item for item in rows if item["user_id"] == user.user_id),
            None,
        )

        return Portfolio.from_dict(user, row) if row is not None else Portfolio(user)

    @staticmethod
    def _replace_portfolio(rows: list[JsonObject], portfolio: Portfolio) -> None:
        """Заменить портфель в списке"""
        rows[:] = [row for row in rows if row["user_id"] != portfolio.user.user_id]
        rows.append(portfolio.to_dict())

    def _cached_rate(
        self,
        from_code: str,
        to_code: str,
        allow_stale: bool = False,
    ) -> RateQuote:
        """Получить курс из кеша с проверкой TTL"""
        get_currency(from_code)
        get_currency(to_code)

        if from_code == to_code:
            return {
                "rate": 1.0,
                "updated_at": to_utc_iso(),
                "source": "Identity",
            }

        snapshot: JsonObject = self.db.read_json(
            "rates_file", {"pairs": {}, "last_refresh": None}
        )
        pairs: JsonObject = snapshot.get("pairs", {})
        ttl: int = self.settings.get("rates_ttl_seconds")

        def one_pair(pair: str) -> RateQuote | None:
            """Найти пару в кеше и проверить ее актуальность"""
            entry: JsonObject | None = pairs.get(pair)

            if entry is None:
                return None

            try:
                rate = validate_positive_amount(entry["rate"])
                updated_at: str = entry["updated_at"]
                timestamp = parse_utc_iso(updated_at)
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                raise ApiRequestError(f"Некорректные данные кеша для {pair}") from exc

            age = (utc_now() - timestamp).total_seconds()
            if not allow_stale and (age > ttl or age < -CACHE_CLOCK_SKEW_SECONDS):
                raise ApiRequestError(
                    f"Курс {pair.replace('_', '→')} устарел. Выполните update-rates"
                )

            return {
                "rate": rate,
                "updated_at": updated_at,
                "source": entry.get("source", "Cache"),
            }

        direct = one_pair(f"{from_code}_{to_code}")
        if direct is not None:
            return direct

        reverse = one_pair(f"{to_code}_{from_code}")
        if reverse is not None:
            return {
                "rate": 1.0 / reverse["rate"],
                "updated_at": reverse["updated_at"],
                "source": reverse["source"],
            }

        if from_code != USD_CODE and to_code != USD_CODE:
            from_usd = one_pair(f"{from_code}_{USD_CODE}")
            to_usd = one_pair(f"{to_code}_{USD_CODE}")

            if from_usd is not None and to_usd is not None:
                updated_at = min(
                    from_usd["updated_at"],
                    to_usd["updated_at"],
                    key=parse_utc_iso,
                )

                return {
                    "rate": from_usd["rate"] / to_usd["rate"],
                    "updated_at": updated_at,
                    "source": "Cross via USD",
                }

        raise ApiRequestError(
            f"Курс {from_code}→{to_code} недоступен. Выполните update-rates"
        )

    def get_rate(self, from_code: str, to_code: str) -> RateResult:
        """Получить обменный курс"""
        quote = self._cached_rate(from_code, to_code)
        return {
            "from": from_code,
            "to": to_code,
            "rate": quote["rate"],
            "updated_at": quote["updated_at"],
            "source": quote["source"],
        }

    def show_portfolio(self, user_id: int, base: str = USD_CODE) -> JsonObject:
        """Показать портфель и общую стоимость"""
        get_currency(base)
        user = self._user_by_id(user_id)
        stored: list[JsonObject] = self.db.read_json("portfolios_file", [])
        portfolio = self._portfolio(user, stored)

        rows: list[JsonObject] = []
        for code, wallet in sorted(portfolio.wallets.items()):
            value = (
                wallet.balance * self._cached_rate(code, base)["rate"]
                if wallet.balance > 0
                else 0.0
            )
            rows.append({"code": code, "balance": wallet.balance, "value": value})

        return {
            "username": user.username,
            "base": base,
            "wallets": rows,
            "total": sum(row["value"] for row in rows),
        }

    @log_action("DEPOSIT")
    def deposit(self, user_id: int, amount: float) -> JsonObject:
        """Пополнить учебный USD-кошелек"""
        amount = validate_positive_amount(amount)
        user = self._user_by_id(user_id)

        def change(rows: list[JsonObject]) -> JsonObject:
            """Изменить USD-баланс и сохранить портфель"""
            portfolio = self._portfolio(user, rows)
            wallet = portfolio.add_currency(USD_CODE)

            before = wallet.balance
            wallet.deposit(amount)
            self._replace_portfolio(rows, portfolio)

            return {
                "before": before,
                "after": wallet.balance,
                "amount": amount,
            }

        return self.db.update_json(
            "portfolios_file",
            list[JsonObject](),
            change,
        )

    @log_action("BUY", verbose=True)
    def buy(self, user_id: int, currency_code: str, amount: float) -> JsonObject:
        """Купить валюту за USD"""
        amount = validate_positive_amount(amount)
        get_currency(currency_code)

        if currency_code == USD_CODE:
            raise ValueError("USD нельзя купить за USD; используйте deposit")

        rate = self._cached_rate(currency_code, USD_CODE)["rate"]
        cost = amount * rate
        user = self._user_by_id(user_id)

        def change(rows: list[JsonObject]) -> JsonObject:
            """Списать USD и зачислить купленную валюту"""
            portfolio = self._portfolio(user, rows)
            usd = portfolio.add_currency(USD_CODE)
            usd_before = usd.balance
            usd.withdraw(cost)

            wallet = portfolio.add_currency(currency_code)
            before = wallet.balance
            wallet.deposit(amount)
            self._replace_portfolio(rows, portfolio)

            return {
                "code": currency_code,
                "amount": amount,
                "rate": rate,
                "base": USD_CODE,
                "cost": cost,
                "before": before,
                "after": wallet.balance,
                "usd_before": usd_before,
                "usd_after": usd.balance,
            }

        return self.db.update_json(
            "portfolios_file",
            list[JsonObject](),
            change,
        )

    @log_action("SELL", verbose=True)
    def sell(self, user_id: int, currency_code: str, amount: float) -> JsonObject:
        """Продать валюту и начислить USD"""
        amount = validate_positive_amount(amount)
        get_currency(currency_code)

        if currency_code == USD_CODE:
            raise ValueError("USD нельзя продать за USD; используйте другую валюту")

        rate = self._cached_rate(currency_code, USD_CODE)["rate"]
        revenue = amount * rate
        user = self._user_by_id(user_id)

        def change(rows: list[JsonObject]) -> JsonObject:
            """Списать валюту и зачислить выручку в USD"""
            portfolio = self._portfolio(user, rows)
            wallet = portfolio.get_wallet(currency_code)

            if wallet is None:
                raise ValueError(
                    f"У вас нет кошелька '{currency_code}'. "
                    "Он создается автоматически при первой покупке"
                )

            before = wallet.balance
            wallet.withdraw(amount)

            usd = portfolio.add_currency(USD_CODE)
            usd_before = usd.balance
            usd.deposit(revenue)
            self._replace_portfolio(rows, portfolio)

            return {
                "code": currency_code,
                "amount": amount,
                "rate": rate,
                "base": USD_CODE,
                "revenue": revenue,
                "before": before,
                "after": wallet.balance,
                "usd_before": usd_before,
                "usd_after": usd.balance,
            }

        return self.db.update_json(
            "portfolios_file",
            list[JsonObject](),
            change,
        )

    def show_rates(
        self,
        currency_code: str | None = None,
        top: int | None = None,
        base: str = USD_CODE,
    ) -> JsonObject:
        """Показать курсы из кеша с фильтрами"""
        get_currency(base)

        if currency_code is not None:
            get_currency(currency_code)

        if top is not None and top <= 0:
            raise ValueError("Параметр --top должен быть положительным")

        snapshot: JsonObject = self.db.read_json(
            "rates_file", {"pairs": {}, "last_refresh": None}
        )
        pairs: JsonObject = snapshot.get("pairs", {})

        if not pairs:
            raise ValueError("Локальный кеш курсов пуст. Выполните 'update-rates'")

        rows: list[JsonObject] = []
        for pair in pairs:
            code, _separator, quoted = pair.partition("_")

            if quoted != USD_CODE or (
                currency_code is not None and code != currency_code
            ):
                continue

            if top is not None and not isinstance(get_currency(code), CryptoCurrency):
                continue

            quote = self._cached_rate(code, base, allow_stale=True)
            rows.append(
                {
                    "pair": f"{code}_{base}",
                    "rate": quote["rate"],
                    "updated_at": quote["updated_at"],
                }
            )

        if not rows:
            if currency_code is not None:
                raise ValueError(f"Курс для '{currency_code}' не найден в кеше")
            raise ValueError("Нет курсов по выбранным фильтрам")

        if top is not None:
            rows.sort(key=lambda row: row["rate"], reverse=True)
            rows = rows[:top]
        else:
            rows.sort(key=lambda row: row["pair"])

        return {
            "rows": rows,
            "last_refresh": snapshot.get("last_refresh"),
        }
