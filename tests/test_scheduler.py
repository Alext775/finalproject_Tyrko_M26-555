"""Тесты фонового обновления курсов"""

import unittest
from threading import Event
from unittest.mock import Mock, patch

from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.scheduler import RatesScheduler
from valutatrade_hub.parser_service.updater import RatesUpdater


class SchedulerTests(unittest.TestCase):
    """Проверки запуска и остановки планировщика"""

    def test_interval_from_settings(self) -> None:
        """Проверить загрузку интервала из настроек"""
        with patch.object(
            SettingsLoader,
            "get",
            return_value=60,
        ):
            scheduler = RatesScheduler()

        self.assertEqual(scheduler.interval_seconds, 60)

    def test_invalid_interval(self) -> None:
        """Проверить запрет некорректного интервала"""
        with self.assertRaises(ValueError):
            RatesScheduler(interval_seconds=0)

        with self.assertRaises(ValueError):
            RatesScheduler(interval_seconds=-1)

    def test_start_and_stop(self) -> None:
        """Проверить запуск и остановку фонового потока"""
        updated = Event()
        updater = Mock(spec=RatesUpdater)

        def fake_update(source: str | None = None) -> dict[str, object]:
            """Вернуть тестовый результат обновления"""
            updated.set()

            return {
                "updated": 1,
                "failures": {},
                "last_refresh": "test",
            }

        updater.run_update.side_effect = fake_update

        with (
            patch.object(
                RatesUpdater,
                "create_default",
                return_value=updater,
            ),
            patch(
                "valutatrade_hub.parser_service.scheduler.load_api_key",
                return_value=None,
            ),
        ):
            scheduler = RatesScheduler(interval_seconds=0.01)

            try:
                scheduler.start()

                self.assertTrue(
                    updated.wait(timeout=2),
                    "Фоновое обновление не выполнилось",
                )

                updater.run_update.assert_called_with(source="coingecko")

            finally:
                scheduler.stop()

        self.assertFalse(scheduler.is_running)


if __name__ == "__main__":
    unittest.main()
