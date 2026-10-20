"""Декоратор для логирования операций"""

import inspect
import logging
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar, cast

P = ParamSpec("P")
R = TypeVar("R")


def log_action(
    action: str,
    verbose: bool = False,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Записать результат операции в лог"""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        """Добавить логирование к функции"""
        signature = inspect.signature(func)

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            """Выполнить функцию с логированием"""
            bound = signature.bind_partial(*args, **kwargs)
            data = bound.arguments

            fields: list[str] = [action]
            logger = logging.getLogger("valutatrade.actions")

            for parameter, label in (
                ("user_id", "user_id"),
                ("currency_code", "currency"),
                ("amount", "amount"),
            ):
                if parameter in data:
                    fields.append(f"{label}={data[parameter]!r}")

            try:
                result = func(*args, **kwargs)

            except Exception as exc:
                logger.info(
                    "%s result=ERROR error_type=%s error_message=%r",
                    " ".join(fields),
                    type(exc).__name__,
                    str(exc),
                )
                raise

            result_object: object = result

            if isinstance(result_object, dict):
                values = cast(dict[str, object], result_object)

                for field in ("rate", "base"):
                    if field in values:
                        fields.append(f"{field}={values[field]!r}")

                if verbose:
                    for field in ("before", "after"):
                        if field in values:
                            fields.append(f"{field}={values[field]!r}")

            logger.info(
                "%s result=OK",
                " ".join(fields),
            )

            return result

        return wrapper

    return decorator
