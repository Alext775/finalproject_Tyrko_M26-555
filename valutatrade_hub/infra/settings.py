"""Singleton для настроек проекта"""

import os
import threading
import tomllib
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SettingsLoader:
    """Единственный экземпляр настроек через __new__"""

    _instance: "SettingsLoader | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "SettingsLoader":
        # __new__ выбран для простой реализации Singleton.
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False

        return cls._instance

    def __init__(self) -> None:
        if not self._initialized:
            self.reload()
            self._initialized = True

    def reload(self) -> None:
        """Перезагрузить настройки"""
        config_file = PROJECT_ROOT / "pyproject.toml"

        with config_file.open("rb") as source:
            values = (
                tomllib.load(source)
                .get("tool", {})
                .get("valutatrade", {})
            )

        data_dir = Path(
            os.getenv(
                "VALUTATRADE_DATA_DIR",
                values.get("data_dir", "data"),
            )
        )

        logs_dir = Path(
            os.getenv(
                "VALUTATRADE_LOGS_DIR",
                values.get("logs_dir", "logs"),
            )
        )

        if not data_dir.is_absolute():
            data_dir = PROJECT_ROOT / data_dir

        if not logs_dir.is_absolute():
            logs_dir = PROJECT_ROOT / logs_dir

        self._config = {
            "data_dir": data_dir,
            "users_file": data_dir / "users.json",
            "portfolios_file": data_dir / "portfolios.json",
            "rates_file": data_dir / "rates.json",
            "history_file": data_dir / "exchange_rates.json",
            "logs_dir": logs_dir,
            "rates_ttl_seconds": int(
                values.get("rates_ttl_seconds", 300)
            ),
            "base_currency": values.get("base_currency", "USD"),
            "log_level": values.get("log_level", "INFO"),
            "log_format": values.get("log_format", "text"),
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Получить настройку"""
        return self._config.get(key, default)