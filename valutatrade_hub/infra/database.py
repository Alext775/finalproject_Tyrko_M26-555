"""JSON-хранилище с атомарной записью"""

import json
import os
import tempfile
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from valutatrade_hub.infra.settings import SettingsLoader


class DatabaseManager:
    """Singleton для чтения и записи JSON"""

    _instance: "DatabaseManager | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "DatabaseManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._lock = threading.RLock()

        return cls._instance

    @property
    def transaction_lock(self) -> threading.RLock:
        """Блокировка для составных операций"""
        return self._lock

    def _path(self, settings_key: str) -> Path:
        path = SettingsLoader().get(settings_key)

        if not isinstance(path, Path):
            raise ValueError(
                f"Неизвестный путь конфигурации: {settings_key}"
            )

        return path

    def read_json(self, settings_key: str, default: Any) -> Any:
        """Прочитать JSON-файл"""
        with self._lock:
            path = self._path(settings_key)

            if not path.exists():
                return deepcopy(default)

            try:
                with path.open(encoding="utf-8") as source:
                    return json.load(source)
            except (json.JSONDecodeError, UnicodeError) as exc:
                raise ValueError(
                    f"Повреждён JSON-файл {path.name}"
                ) from exc

    def write_json(self, settings_key: str, value: Any) -> None:
        """Атомарная запись через временный файл"""
        with self._lock:
            path = self._path(settings_key)
            path.parent.mkdir(parents=True, exist_ok=True)

            temp_path: str | None = None

            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=path.parent,
                    prefix=f".{path.stem}-",
                    suffix=".tmp",
                    delete=False,
                ) as temp:
                    temp_path = temp.name
                    json.dump(value, temp, ensure_ascii=False, indent=2)
                    temp.write("\n")
                    temp.flush()
                    os.fsync(temp.fileno())

                os.replace(temp_path, path)

            finally:
                if temp_path is not None and os.path.exists(temp_path):
                    os.unlink(temp_path)

    def update_json(
        self,
        settings_key: str,
        default: Any,
        change: Callable[[Any], Any],
    ) -> Any:
        """Выполнить чтение, изменение и запись под блокировкой"""
        with self._lock:
            current = self.read_json(settings_key, default)
            result = change(current)
            self.write_json(settings_key, current)
            return result