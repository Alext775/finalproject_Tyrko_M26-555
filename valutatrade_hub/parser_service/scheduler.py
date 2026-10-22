"""Автоматическое обновление курсов в фоновом потоке"""

import logging
from threading import Event, Thread

from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.credentials import load_api_key
from valutatrade_hub.parser_service.updater import RatesUpdater

DEFAULT_INTERVAL_SECONDS = 300


class RatesScheduler:
    """Планировщик периодического обновления курсов"""

    def __init__(self, interval_seconds: float | None = None) -> None:
        if interval_seconds is None:
            interval_seconds = int(
                SettingsLoader().get(
                    "rates_ttl_seconds",
                    DEFAULT_INTERVAL_SECONDS,
                )
            )

        if interval_seconds <= 0:
            raise ValueError("Интервал должен быть положительным")

        self._interval_seconds = interval_seconds
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._logger = logging.getLogger("valutatrade.parser")

    @property
    def interval_seconds(self) -> float:
        """Получить интервал автоматического обновления"""
        return self._interval_seconds

    @property
    def is_running(self) -> bool:
        """Проверить состояние фонового потока"""
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        """Периодически получать и сохранять курсы"""
        while not self._stop_event.wait(self._interval_seconds):
            try:
                source = None if load_api_key() else "coingecko"

                updater = RatesUpdater.create_default()
                result = updater.run_update(source=source)

                self._logger.info(
                    "Автоматическое обновление: сохранено %s курсов",
                    result["updated"],
                )

                for provider, error in result["failures"].items():
                    self._logger.warning(
                        "Ошибка источника %s: %s",
                        provider,
                        error,
                    )

            except Exception:
                # Фоновый поток не должен завершаться из-за ошибки API
                self._logger.exception("Не удалось автоматически обновить курсы")

    def start(self) -> None:
        """Запустить фоновое обновление"""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()

        self._thread = Thread(
            target=self._run,
            name="valutatrade-rates",
            daemon=False,
        )

        self._thread.start()

    def stop(self) -> None:
        """Остановить фоновое обновление"""
        self._stop_event.set()

        thread = self._thread

        if thread is not None:
            thread.join()
            self._thread = None
