"""Бизнес-логика валютного кошелька"""

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


class UseCases:
    """Основные операции приложения"""

    def __init__(
        self,
        db: DatabaseManager | None = None,
        settings: SettingsLoader | None = None,
    ) -> None:
        self.db = db or DatabaseManager()
        self.settings = settings or SettingsLoader()

    def register(self, username: str, password: str) -> dict:
        """Зарегистрировать пользователя"""
        if not isinstance(username, str) or not username.strip():
            raise ValueError("Имя пользователя не может быть пустым")

        with self.db.transaction_lock:
            rows = self.db.read_json("users_file", [])

            if any(row["username"] == username.strip() for row in rows):
                raise ValueError(
                    f"Имя пользователя '{username.strip()}' уже занято"
                )

            new_id = max(
                (row["user_id"] for row in rows),
                default=0,
            ) + 1

            user = User.create(new_id, username, password)

            portfolios = self.db.read_json("portfolios_file", [])
            portfolios.append(Portfolio(user).to_dict())
            rows.append(user.to_dict())

            self.db.write_json("portfolios_file", portfolios)
            self.db.write_json("users_file", rows)

        return user.get_user_info()

    def login(self, username: str, password: str) -> dict:
        """Авторизовать пользователя"""
        rows = self.db.read_json("users_file", [])

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
        for row in self.db.read_json("users_file", []):
            if row["user_id"] == user_id:
                return User.from_dict(row)

        raise ValueError("Пользователь не найден. Выполните login")

    def _portfolio(
        self,
        user: User,
        rows: list[dict],
    ) -> Portfolio:
        """Получить портфель пользователя"""
        row = next(
            (
                item
                for item in rows
                if item["user_id"] == user.user_id
            ),
            None,
        )

        return (
            Portfolio.from_dict(user, row)
            if row
            else Portfolio(user)
        )

    @staticmethod
    def _replace_portfolio(
        rows: list[dict],
        portfolio: Portfolio,
    ) -> None:
        """Заменить портфель в списке"""
        rows[:] = [
            row
            for row in rows
            if row["user_id"] != portfolio.user.user_id
        ] + [portfolio.to_dict()]

    def _cached_rate(
        self,
        from_code: str,
        to_code: str,
        allow_stale: bool = False,
    ) -> dict:
        """Получить курс из кеша с проверкой TTL"""
        get_currency(from_code)
        get_currency(to_code)

        if from_code == to_code:
            return {
                "rate": 1.0,
                "updated_at": to_utc_iso(),
                "source": "Identity",
            }

        snapshot = self.db.read_json(
            "rates_file",
            {"pairs": {}, "last_refresh": None},
        )

        pairs = snapshot.get("pairs", {})
        ttl = self.settings.get("rates_ttl_seconds")

        def one_pair(pair: str) -> dict | None:
            entry = pairs.get(pair)

            if not entry:
                return None

            try:
                rate = validate_positive_amount(entry["rate"])
                timestamp = parse_utc_iso(entry["updated_at"])

            except (ValueError, KeyError, TypeError) as exc:
                raise ApiRequestError(
                    f"Некорректные данные кеша для {pair}"
                ) from exc

            age = (utc_now() - timestamp).total_seconds()

            if not allow_stale and (
                age > ttl
                or age < -CACHE_CLOCK_SKEW_SECONDS
            ):
                raise ApiRequestError(
                    f"Курс {pair.replace('_', '→')} устарел. "
                    "Выполните update-rates"
                )

            return {
                "rate": rate,
                "updated_at": entry["updated_at"],
                "source": entry.get("source", "Cache"),
            }

        direct = one_pair(f"{from_code}_{to_code}")

        if direct:
            return direct

        reverse = one_pair(f"{to_code}_{from_code}")

        if reverse:
            return {
                **reverse,
                "rate": 1 / reverse["rate"],
            }

        # Кросс-курс через USD.
        if from_code != "USD" and to_code != "USD":
            from_usd = one_pair(f"{from_code}_USD")
            to_usd = one_pair(f"{to_code}_USD")

            if from_usd and to_usd:
                updated_at = min(
                    (
                        from_usd["updated_at"],
                        to_usd["updated_at"],
                    ),
                    key=parse_utc_iso,
                )

                return {
                    "rate": from_usd["rate"] / to_usd["rate"],
                    "updated_at": updated_at,
                    "source": "Cross via USD",
                }

        raise ApiRequestError(
            f"Курс {from_code}→{to_code} недоступен. "
            "Выполните update-rates"
        )

    def get_rate(
        self,
        from_code: str,
        to_code: str,
    ) -> dict:
        """Получить обменный курс"""
        return {
            "from": from_code,
            "to": to_code,
            **self._cached_rate(from_code, to_code),
        }

    def show_portfolio(
        self,
        user_id: int,
        base: str = "USD",
    ) -> dict:
        """Показать портфель и общую стоимость"""
        get_currency(base)

        user = self._user_by_id(user_id)

        portfolio = self._portfolio(
            user,
            self.db.read_json("portfolios_file", []),
        )

        rows = []

        for code, wallet in sorted(portfolio.wallets.items()):
            worth = (
                wallet.balance * self._cached_rate(code, base)["rate"]
                if wallet.balance
                else 0.0
            )

            rows.append({
                "code": code,
                "balance": wallet.balance,
                "value": worth,
            })

        return {
            "username": user.username,
            "base": base,
            "wallets": rows,
            "total": sum(row["value"] for row in rows),
        }

    @log_action("DEPOSIT")
    def deposit(
        self,
        user_id: int,
        amount: float,
    ) -> dict:
        """Пополнить учебный USD-кошелек"""
        amount = validate_positive_amount(amount)
        user = self._user_by_id(user_id)

        def change(rows: list[dict]) -> dict:
            portfolio = self._portfolio(user, rows)
            wallet = portfolio.add_currency("USD")

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
            [],
            change,
        )

    @log_action("BUY", verbose=True)
    def buy(
        self,
        user_id: int,
        currency_code: str,
        amount: float,
    ) -> dict:
        """Купить валюту за USD"""
        amount = validate_positive_amount(amount)
        get_currency(currency_code)

        if currency_code == "USD":
            raise ValueError(
                "USD нельзя купить за USD; используйте deposit"
            )

        rate = self.get_rate(currency_code, "USD")["rate"]
        cost = amount * rate
        user = self._user_by_id(user_id)

        def change(rows: list[dict]) -> dict:
            portfolio = self._portfolio(user, rows)

            usd = portfolio.add_currency("USD")
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
                "base": "USD",
                "cost": cost,
                "before": before,
                "after": wallet.balance,
                "usd_before": usd_before,
                "usd_after": usd.balance,
            }

        return self.db.update_json(
            "portfolios_file",
            [],
            change,
        )

    @log_action("SELL", verbose=True)
    def sell(
        self,
        user_id: int,
        currency_code: str,
        amount: float,
    ) -> dict:
        """Продать валюту и начислить USD"""
        amount = validate_positive_amount(amount)
        get_currency(currency_code)

        if currency_code == "USD":
            raise ValueError(
                "USD нельзя продать за USD; используйте другую валюту"
            )

        rate = self.get_rate(currency_code, "USD")["rate"]
        revenue = amount * rate
        user = self._user_by_id(user_id)

        def change(rows: list[dict]) -> dict:
            portfolio = self._portfolio(user, rows)
            wallet = portfolio.get_wallet(currency_code)

            if wallet is None:
                raise ValueError(
                    f"У вас нет кошелька '{currency_code}'. "
                    "Он создается автоматически при первой покупке"
                )

            before = wallet.balance
            wallet.withdraw(amount)

            usd = portfolio.add_currency("USD")
            usd_before = usd.balance
            usd.deposit(revenue)

            self._replace_portfolio(rows, portfolio)

            return {
                "code": currency_code,
                "amount": amount,
                "rate": rate,
                "base": "USD",
                "revenue": revenue,
                "before": before,
                "after": wallet.balance,
                "usd_before": usd_before,
                "usd_after": usd.balance,
            }

        return self.db.update_json(
            "portfolios_file",
            [],
            change,
        )

    def show_rates(
        self,
        currency_code: str | None = None,
        top: int | None = None,
        base: str = "USD",
    ) -> dict:
        """Показать курсы из кеша с фильтрами"""
        get_currency(base)

        if currency_code:
            get_currency(currency_code)

        if top is not None and top <= 0:
            raise ValueError(
                "Параметр --top должен быть положительным"
            )

        snapshot = self.db.read_json(
            "rates_file",
            {"pairs": {}, "last_refresh": None},
        )

        pairs = snapshot.get("pairs", {})

        if not pairs:
            raise ValueError(
                "Локальный кеш курсов пуст. Выполните 'update-rates'"
            )

        rows = []

        for pair in pairs:
            code, _separator, quoted = pair.partition("_")

            if quoted != "USD" or (
                currency_code and code != currency_code
            ):
                continue

            if top is not None and not isinstance(
                get_currency(code),
                CryptoCurrency,
            ):
                continue

            quote = self._cached_rate(
                code,
                base,
                allow_stale=True,
            )

            rows.append({
                "pair": f"{code}_{base}",
                "rate": quote["rate"],
                "updated_at": quote["updated_at"],
            })

        if not rows:
            if currency_code:
                raise ValueError(
                    f"Курс для '{currency_code}' не найден в кеше"
                )

            raise ValueError(
                "Нет курсов по выбранным фильтрам"
            )

        if top is not None:
            rows.sort(
                key=lambda row: row["rate"],
                reverse=True,
            )
            rows = rows[:top]
        else:
            rows.sort(key=lambda row: row["pair"])

        return {
            "rows": rows,
            "last_refresh": snapshot.get("last_refresh"),
        }