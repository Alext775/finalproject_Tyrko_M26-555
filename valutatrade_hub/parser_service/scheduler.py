"""Автоматическое обновление курсов по расписанию"""

import logging
import time

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import configure_logging
from valutatrade_hub.parser_service.updater import RatesUpdater

DEFAULT_INTERVAL_SECONDS = 300


def run_scheduler(
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
) -> None:
    """Периодически обновлять курсы"""
    if interval_seconds <= 0:
        raise ValueError(
            "Интервал должен быть положительным"
        )

    configure_logging()
    logger = logging.getLogger("valutatrade.parser")

    try:
        while True:
            try:
                RatesUpdater.create_default().run_update()

            except ApiRequestError as exc:
                logger.error(
                    "Обновление не выполнено: %s",
                    exc,
                )

            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        print("Планировщик остановлен")


if __name__ == "__main__":
    run_scheduler()