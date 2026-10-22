"""Singleton для настроек проекта"""

import os
import threading
import tomllib
from _thread import LockType
from pathlib import Path
from typing import Any, ClassVar

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DATA_DIR = "data"
DEFAULT_LOGS_DIR = "logs"
DEFAULT_RATES_TTL = 300
DEFAULT_BASE_CURRENCY = "USD"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT = "text"


class SettingsLoader:
    """Единственный экземпляр настроек через __new__"""

    _instance: ClassVar["SettingsLoader | None"] = None
    _instance_lock: ClassVar[LockType] = threading.Lock()

    def __new__(cls) -> "SettingsLoader":
        """Создать или вернуть единственный экземпляр"""
        # __new__ выбран из-за простоты и читаемости
        with cls._instance_lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._initialized = False
                cls._instance = instance

        return cls._instance

    def __init__(self) -> None:
        if not self._initialized:
            self.reload()
            self._initialized = True

    @staticmethod
    def _absolute_path(value: str) -> Path:
        """Преобразовать путь относительно корня проекта"""
        path = Path(value)

        if not path.is_absolute():
            path = PROJECT_ROOT / path

        return path.resolve()

    def reload(self) -> None:
        """Перезагрузить настройки из pyproject.toml"""
        config_file = PROJECT_ROOT / "pyproject.toml"

        with config_file.open("rb") as source:
            document: dict[str, Any] = tomllib.load(source)

        values: dict[str, Any] = document.get("tool", {}).get("valutatrade", {})

        data_dir = self._absolute_path(
            os.getenv(
                "VALUTATRADE_DATA_DIR",
                str(values.get("data_dir", DEFAULT_DATA_DIR)),
            )
        )

        logs_dir = self._absolute_path(
            os.getenv(
                "VALUTATRADE_LOGS_DIR",
                str(values.get("logs_dir", DEFAULT_LOGS_DIR)),
            )
        )

        self._config: dict[str, Any] = {
            "data_dir": data_dir,
            "users_file": data_dir / "users.json",
            "portfolios_file": data_dir / "portfolios.json",
            "rates_file": data_dir / "rates.json",
            "history_file": data_dir / "exchange_rates.json",
            "logs_dir": logs_dir,
            "rates_ttl_seconds": int(
                values.get("rates_ttl_seconds", DEFAULT_RATES_TTL)
            ),
            "base_currency": str(values.get("base_currency", DEFAULT_BASE_CURRENCY)),
            "log_level": str(values.get("log_level", DEFAULT_LOG_LEVEL)),
            "log_format": str(values.get("log_format", DEFAULT_LOG_FORMAT)),
        }

        if self._config["rates_ttl_seconds"] <= 0:
            raise ValueError("rates_ttl_seconds должен быть положительным")

    def get(self, key: str, default: Any = None) -> Any:
        """Получить значение настройки"""
        return self._config.get(key, default)
