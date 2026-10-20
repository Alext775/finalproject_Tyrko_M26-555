"""Консольный интерфейс ValutaTrade Hub"""

import argparse
import shlex

from prettytable import PrettyTable

from valutatrade_hub.core.currencies import CURRENCY_REGISTRY
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.usecases import UseCases
from valutatrade_hub.logging_config import configure_logging
from valutatrade_hub.parser_service.updater import RatesUpdater


class CliArgumentParser(argparse.ArgumentParser):
    """Обработка неправильных аргументов"""

    def error(self, message: str) -> None:
        """Вызвать исключение вместо завершения программы"""
        raise ValueError(
            f"Неверные аргументы: {message}"
        )


def make_parsers() -> dict[str, CliArgumentParser]:
    """Создать парсеры для команд"""
    definitions = {
        "register": (
            ("--username", {"required": True}),
            ("--password", {"required": True}),
        ),
        "login": (
            ("--username", {"required": True}),
            ("--password", {"required": True}),
        ),
        "deposit": (
            ("--amount", {"required": True, "type": float}),
        ),
        "show-portfolio": (
            ("--base", {"default": "USD"}),
        ),
        "buy": (
            ("--currency", {"required": True}),
            ("--amount", {"required": True, "type": float}),
        ),
        "sell": (
            ("--currency", {"required": True}),
            ("--amount", {"required": True, "type": float}),
        ),
        "get-rate": (
            ("--from", {"dest": "from_code", "required": True}),
            ("--to", {"dest": "to_code", "required": True}),
        ),
        "update-rates": (
            (
                "--source",
                {"choices": ["coingecko", "exchangerate"]},
            ),
        ),
        "show-rates": (
            ("--currency", {}),
            ("--top", {"type": int}),
            ("--base", {"default": "USD"}),
        ),
    }

    parsers = {}

    for name, arguments in definitions.items():
        parser = CliArgumentParser(
            prog=name,
            add_help=False,
        )

        for flag, options in arguments:
            parser.add_argument(flag, **options)

        parsers[name] = parser

    return parsers


class WalletCLI:
    """Интерактивный интерфейс валютного кошелька"""

    def __init__(
        self,
        usecases: UseCases | None = None,
    ) -> None:
        self.usecases = usecases or UseCases()
        self.user_id: int | None = None
        self.parsers = make_parsers()

    def _require_login(self) -> int:
        """Убедиться, что пользователь вошел в систему"""
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
        if command:
            parser = self.parsers.get(command)

            if parser is None:
                print(f"Неизвестная команда '{command}'")
            else:
                print(parser.format_usage().strip())

            return

        print("Команды: " + ", ".join(self.parsers))
        print("Дополнительно: help [команда], logout, exit")
        print(
            "Поддерживаемые валюты: "
            + ", ".join(CURRENCY_REGISTRY)
        )

    def execute(self, line: str) -> bool:
        """Выполнить одну команду"""
        if not line.strip():
            return True

        try:
            parts = shlex.split(line)
            command, *tokens = parts

            if command == "exit":
                if tokens:
                    raise ValueError(
                        "exit не принимает аргументы"
                    )
                return False

            if command == "help":
                if len(tokens) > 1:
                    raise ValueError(
                        "Формат: help [команда]"
                    )

                self.help(tokens[0] if tokens else None)
                return True

            if command == "logout":
                if tokens:
                    raise ValueError(
                        "logout не принимает аргументы"
                    )

                self.user_id = None
                print("Вы вышли из системы")
                return True

            parser = self.parsers.get(command)

            if parser is None:
                raise ValueError(
                    f"Неизвестная команда '{command}'. Введите help"
                )

            arguments = parser.parse_args(tokens)
            self._dispatch(command, arguments)

        except (
            ValueError,
            OSError,
            ApiRequestError,
            CurrencyNotFoundError,
            InsufficientFundsError,
        ) as exc:
            print(f"Ошибка: {exc}")

            if isinstance(exc, CurrencyNotFoundError):
                print(
                    "Доступные коды: "
                    + ", ".join(CURRENCY_REGISTRY)
                )

            elif isinstance(exc, ApiRequestError):
                print(
                    "Проверьте сеть или повторите "
                    "update-rates позже"
                )

        return True

    def _dispatch(
        self,
        command: str,
        args: argparse.Namespace,
    ) -> None:
        """Вызвать нужную бизнес-операцию"""
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

            self.user_id = result["user_id"]
            print(f"Вы вошли как '{result['username']}'")

        elif command == "deposit":
            result = service.deposit(
                self._require_login(),
                args.amount,
            )

            print(
                f"USD пополнен: "
                f"{result['before']:.2f} → "
                f"{result['after']:.2f} USD"
            )

        elif command == "show-portfolio":
            result = service.show_portfolio(
                self._require_login(),
                args.base,
            )

            print(
                f"Портфель '{result['username']}' "
                f"(база: {result['base']}):"
            )

            if not result["wallets"]:
                print("Кошельков пока нет")

            else:
                print(
                    self._format_table(
                        [
                            "Валюта",
                            "Баланс",
                            f"Стоимость ({result['base']})",
                        ],
                        [
                            [
                                row["code"],
                                f"{row['balance']:.4f}",
                                f"{row['value']:,.2f}",
                            ]
                            for row in result["wallets"]
                        ],
                    )
                )

            print(
                f"ИТОГО: {result['total']:,.2f} "
                f"{result['base']}"
            )

        elif command in ("buy", "sell"):
            operation = (
                service.buy
                if command == "buy"
                else service.sell
            )

            result = operation(
                self._require_login(),
                args.currency,
                args.amount,
            )

            name = (
                "Покупка"
                if command == "buy"
                else "Продажа"
            )

            key = (
                "cost"
                if command == "buy"
                else "revenue"
            )

            print(
                f"{name} выполнена: "
                f"{result['amount']:.4f} {result['code']} "
                f"по курсу {result['rate']:.6f} "
                f"USD/{result['code']}"
            )

            print(
                f"{result['code']}: "
                f"{result['before']:.4f} → "
                f"{result['after']:.4f}"
            )

            print(
                f"USD: {result['usd_before']:.2f} → "
                f"{result['usd_after']:.2f}"
            )

            print(
                f"Стоимость / выручка: "
                f"{result[key]:,.2f} USD"
            )

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

            print(
                f"Обратный курс "
                f"{args.to_code}→{args.from_code}: "
                f"{1 / result['rate']:.8f}"
            )

        elif command == "update-rates":
            result = (
                RatesUpdater.create_default()
                .run_update(args.source)
            )

            print(
                f"Обновлено курсов: {result['updated']}"
            )

            print(
                f"Последнее обновление: "
                f"{result['last_refresh']}"
            )

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

            print(
                f"Курсы из кеша "
                f"(обновление: {result['last_refresh']}):"
            )

            print(
                self._format_table(
                    ["Пара", "Курс", "Время UTC"],
                    [
                        [
                            row["pair"],
                            f"{row['rate']:.8f}",
                            row["updated_at"],
                        ]
                        for row in result["rows"]
                    ],
                )
            )

    def run(self) -> None:
        """Запустить цикл команд"""
        print(
            "ValutaTrade Hub. "
            "Введите help для списка команд."
        )

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
    WalletCLI().run()


if __name__ == "__main__":
    main()