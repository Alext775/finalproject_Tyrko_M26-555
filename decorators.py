"""Декоратор для логирования операций"""

import inspect
import logging
from functools import wraps
from typing import Callable


def log_action(action: str, verbose: bool = False) -> Callable:
    """Записать результат операции в лог"""

    def decorator(func: Callable) -> Callable:
        signature = inspect.signature(func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            bound = signature.bind_partial(*args, **kwargs)
            data = bound.arguments
            fields = [action]

            for parameter, label in (
                ("user_id", "user_id"),
                ("currency_code", "currency"),
                ("amount", "amount"),
            ):
                if parameter in data:
                    fields.append(
                        f"{label}={data[parameter]!r}"
                    )

            logger = logging.getLogger("valutatrade.actions")

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

            if isinstance(result, dict):
                for field in ("rate", "base"):
                    if field in result:
                        fields.append(
                            f"{field}={result[field]!r}"
                        )

                if verbose:
                    for field in ("before", "after"):
                        if field in result:
                            fields.append(
                                f"{field}={result[field]!r}"
                            )

            logger.info(
                "%s result=OK",
                " ".join(fields),
            )

            return result

        return wrapper

    return decorator