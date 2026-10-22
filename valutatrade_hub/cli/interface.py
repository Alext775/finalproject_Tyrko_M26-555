"""Консольный интерфейс ValutaTrade Hub"""

import argparse
import shlex
from typing import NoReturn, TypedDict, cast

from prettytable import PrettyTable

from valutatrade_hub.core.currencies import CURRENCY_REGISTRY
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
)
from valutatrade_hub.core.usecases import UseCases
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.logging_config import configure_logging
from valutatrade_hub.parser_service.credentials import (
    configure_api_key,
    load_api_key,
)
from valutatrade_hub.parser_service.scheduler import RatesScheduler
from valutatrade_hub.parser_service.updater import RatesUpdater


class PortfolioRow(TypedDict):
    """Строка таблицы портфеля"""

    code: str
    balance: float
    value: float


class RateRow(TypedDict):
    """Строка таблицы курсов"""

    pair: str
    rate: float
    updated_at: str


class CliArgumentParser(argparse.ArgumentParser):
    """Обработка неправильных аргументов"""

    def error(self, message: str) -> NoReturn:
        """Вызвать исключение вместо завершения программы"""
        raise ValueError(f"Неверные аргументы: {message}")


def make_parsers() -> dict[str, CliArgumentParser]:
    """Создать парсеры для команд"""
    parsers: dict[str, CliArgumentParser] = {}

    register = CliArgumentParser(
        prog="register",
        add_help=False,
    )
    register.add_argument("--username", required=True)
    register.add_argument("--password", required=True)
    parsers["register"] = register

    login = CliArgumentParser(
        prog="login",
        add_help=False,
    )
    login.add_argument("--username", required=True)
    login.add_argument("--password", required=True)
    parsers["login"] = login

    deposit = CliArgumentParser(
        prog="deposit",
        add_help=False,
    )
    deposit.add_argument(
        "--amount",
        required=True,
        type=float,
    )
    parsers["deposit"] = deposit

    show_portfolio = CliArgumentParser(
        prog="show-portfolio",
        add_help=False,
    )
    show_portfolio.add_argument(
        "--base",
        default="USD",
    )
    parsers["show-portfolio"] = show_portfolio

    for command in ("buy", "sell"):
        parser = CliArgumentParser(
            prog=command,
            add_help=False,
        )
        parser.add_argument(
            "--currency",
            required=True,
        )
        parser.add_argument(
            "--amount",
            required=True,
            type=float,
        )
        parsers[command] = parser

    get_rate = CliArgumentParser(
        prog="get-rate",
        add_help=False,
    )
    get_rate.add_argument(
        "--from",
        dest="from_code",
        required=True,
    )
    get_rate.add_argument(
        "--to",
        dest="to_code",
        required=True,
    )
    parsers["get-rate"] = get_rate

    update_rates = CliArgumentParser(
        prog="update-rates",
        add_help=False,
    )
    update_rates.add_argument(
        "--source",
        choices=("coingecko", "exchangerate"),
    )
    parsers["update-rates"] = update_rates

    show_rates = CliArgumentParser(
        prog="show-rates",
        add_help=False,
    )
    show_rates.add_argument("--currency")
    show_rates.add_argument("--top", type=int)
    show_rates.add_argument(
        "--base",
        default="USD",
    )
    parsers["show-rates"] = show_rates

    return parsers


class WalletCLI:
    """Интерактивный интерфейс валютного кошелька"""

    def __init__(
        self,
        usecases: UseCases | None = None,
    ) -> None:
        self.usecases = usecases if usecases is not None else UseCases()
        self.user_id: int | None = None
        self.parsers = make_parsers()

    def _require_login(self) -> int:
        """Проверить авторизацию пользователя"""
        if self.user_id is None:
            raise ValueError("Сначала выполните login")

        return self.user_id

    @staticmethod
    def _format_table(
        headers: list[str],
        rows: list[list[str]],
    ) -> str:
        """Создать таблицу с PrettyTable"""
        table = PrettyTable()
        table.field_names = headers

        for row in rows:
            table.add_row(row)

        return str(table)

    def help(self, command: str | None = None) -> None:
        """Показать список команд"""
        if command is not None:
            parser = self.parsers.get(command)

            if parser is None:
                print(f"Неизвестная команда '{command}'")
            else:
                print(parser.format_usage().strip())

            return

        print("Команды: " + ", ".join(self.parsers))
        print("Дополнительно: help [команда], set-api-key, logout, exit")
        print("Поддерживаемые валюты: " + ", ".join(CURRENCY_REGISTRY))

    def execute(self, line: str) -> bool:
        """Выполнить одну пользовательскую команду"""
        if not line.strip():
            return True

        try:
            parts = shlex.split(line)
            command, *tokens = parts

            if command == "exit":
                if tokens:
                    raise ValueError("exit не принимает аргументы")

                return False

            if command == "help":
                if len(tokens) > 1:
                    raise ValueError("Формат: help [команда]")

                selected = tokens[0] if tokens else None
                self.help(selected)
                return True

            if command == "logout":
                if tokens:
                    raise ValueError("logout не принимает аргументы")

                self.user_id = None
                print("Вы вышли из системы")
                return True

            if command == "set-api-key":
                if tokens:
                    raise ValueError("set-api-key не принимает аргументы")

                configure_api_key(force=True)
                return True

            parser = self.parsers.get(command)

            if parser is None:
                raise ValueError(f"Неизвестная команда '{command}'. Введите help")

            arguments = parser.parse_args(tokens)
            self._dispatch(command, arguments)

        except (ValueError, OSError, ApiRequestError) as exc:
            print(f"Ошибка: {exc}")

            if isinstance(exc, CurrencyNotFoundError):
                print("Доступные коды: " + ", ".join(CURRENCY_REGISTRY))

            elif isinstance(exc, ApiRequestError):
                print("Проверьте сеть или повторите update-rates позже")

        return True

    def _dispatch(
        self,
        command: str,
        args: argparse.Namespace,
    ) -> None:
        """Вызвать соответствующую бизнес-операцию"""
        service = self.usecases

        if command == "register":
            result = service.register(
                args.username,
                args.password,
            )

            print(
                f"Пользователь '{result['username']}' "
                f"зарегистрирован (id={result['user_id']}). "
                f"Войдите: login --username "
                f"{result['username']} --password ****"
            )

        elif command == "login":
            result = service.login(
                args.username,
                args.password,
            )

            self.user_id = int(result["user_id"])
            print(f"Вы вошли как '{result['username']}'")

        elif command == "deposit":
            result = service.deposit(
                self._require_login(),
                args.amount,
            )

            print(f"USD пополнен: {result['before']:.2f} → {result['after']:.2f} USD")

        elif command == "show-portfolio":
            result = service.show_portfolio(
                self._require_login(),
                args.base,
            )

            print(f"Портфель '{result['username']}' (база: {result['base']}):")

            portfolio_rows = cast(
                list[PortfolioRow],
                result["wallets"],
            )

            if not portfolio_rows:
                print("Кошельков пока нет")

            else:
                table_rows: list[list[str]] = [
                    [
                        row["code"],
                        f"{row['balance']:.4f}",
                        f"{row['value']:,.2f}",
                    ]
                    for row in portfolio_rows
                ]

                print(
                    self._format_table(
                        [
                            "Валюта",
                            "Баланс",
                            f"Стоимость ({result['base']})",
                        ],
                        table_rows,
                    )
                )

            print(f"ИТОГО: {result['total']:,.2f} {result['base']}")

        elif command in ("buy", "sell"):
            if command == "buy":
                result = service.buy(
                    self._require_login(),
                    args.currency,
                    args.amount,
                )
                operation_name = "Покупка"
                value_key = "cost"

            else:
                result = service.sell(
                    self._require_login(),
                    args.currency,
                    args.amount,
                )
                operation_name = "Продажа"
                value_key = "revenue"

            print(
                f"{operation_name} выполнена: "
                f"{result['amount']:.4f} {result['code']} "
                f"по курсу {result['rate']:.6f} "
                f"USD/{result['code']}"
            )

            print(f"{result['code']}: {result['before']:.4f} → {result['after']:.4f}")

            print(f"USD: {result['usd_before']:.2f} → {result['usd_after']:.2f}")

            print(f"Стоимость / выручка: {result[value_key]:,.2f} USD")

        elif command == "get-rate":
            result = service.get_rate(
                args.from_code,
                args.to_code,
            )

            print(
                f"Курс {args.from_code}→{args.to_code}: "
                f"{result['rate']:.8f} "
                f"(обновлено: {result['updated_at']})"
            )

            reverse_rate = 1.0 / result["rate"]

            print(f"Обратный курс {args.to_code}→{args.from_code}: {reverse_rate:.8f}")

        elif command == "update-rates":
            updater = RatesUpdater.create_default()
            result = updater.run_update(args.source)

            print(f"Обновлено курсов: {result['updated']}")
            print(f"Последнее обновление: {result['last_refresh']}")

            if result["failures"]:
                print("Частичные ошибки:")

                for source, message in result["failures"].items():
                    print(f"- {source}: {message}")

        elif command == "show-rates":
            result = service.show_rates(
                args.currency,
                args.top,
                args.base,
            )

            print(f"Курсы из кеша (обновление: {result['last_refresh']}):")

            rate_rows = cast(
                list[RateRow],
                result["rows"],
            )

            table_rows: list[list[str]] = [
                [
                    row["pair"],
                    f"{row['rate']:.8f}",
                    row["updated_at"],
                ]
                for row in rate_rows
            ]

            print(
                self._format_table(
                    ["Пара", "Курс", "Время UTC"],
                    table_rows,
                )
            )

    def run(self) -> None:
        """Запустить цикл пользовательских команд"""
        print("ValutaTrade Hub. Введите help для списка команд.")

        while True:
            try:
                line = input("> ")

            except (EOFError, KeyboardInterrupt):
                print("\nЗавершение работы")
                break

            if not self.execute(line):
                print("Завершение работы")
                break


def main() -> None:
    """Главная точка входа CLI"""
    configure_logging()

    DatabaseManager().initialize_files()

    print("Запуск ValutaTrade Hub")

    configure_api_key()

    print("\nПолучение актуальных курсов...")

    try:
        source = None if load_api_key() else "coingecko"

        updater = RatesUpdater.create_default()
        result = updater.run_update(source=source)

        print(f"Обновлено курсов: {result['updated']}")

        if result["failures"]:
            print("Некоторые источники недоступны:")

            for provider, error in result["failures"].items():
                print(f"- {provider}: {error}")

    except (ApiRequestError, OSError, ValueError) as exc:
        print(f"Не удалось обновить курсы: {exc}")
        print("Продолжение работы с локальным кешем")

    scheduler = RatesScheduler()
    scheduler.start()

    print("Автоматическое обновление курсов включено")
    print(
        f"Интервал обновления: "
        f"{scheduler.interval_seconds} сек."
    )

    try:
        WalletCLI().run()

    finally:
        scheduler.stop()


if __name__ == "__main__":
    main()
