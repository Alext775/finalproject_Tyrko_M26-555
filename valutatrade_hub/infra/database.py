"""JSON-хранилище с атомарной записью"""

import json
import os
import tempfile
import threading
from _thread import LockType, RLock
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from valutatrade_hub.infra.settings import SettingsLoader

T = TypeVar("T")
R = TypeVar("R")


class DatabaseManager:
    """Singleton для чтения и записи JSON"""

    _instance: ClassVar["DatabaseManager | None"] = None
    _instance_lock: ClassVar[LockType] = threading.Lock()

    _lock: RLock

    def __new__(cls) -> "DatabaseManager":
        """Создать или вернуть единственный экземпляр"""
        with cls._instance_lock:
            instance = cls._instance

            if instance is None:
                instance = super().__new__(cls)
                instance._lock = RLock()
                cls._instance = instance

            return instance

    @property
    def transaction_lock(self) -> RLock:
        """Получить блокировку для составных операций"""
        return self._lock

    @staticmethod
    def _path(settings_key: str) -> Path:
        """Получить путь к JSON-файлу"""
        configured_path: object = SettingsLoader().get(settings_key)

        if not isinstance(configured_path, Path):
            raise ValueError(f"Неизвестный путь конфигурации: {settings_key}")

        return configured_path

    def read_json(self, settings_key: str, default: T) -> T:
        """Прочитать JSON-файл"""
        with self._lock:
            path = self._path(settings_key)

            if not path.exists():
                return deepcopy(default)

            try:
                with path.open(encoding="utf-8") as source:
                    data: object = json.load(source)

                return cast(T, data)

            except (json.JSONDecodeError, UnicodeError) as exc:
                raise ValueError(f"Поврежден JSON-файл {path.name}") from exc

    def write_json(self, settings_key: str, value: object) -> None:
        """Атомарно записать JSON-файл"""
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

                    json.dump(
                        value,
                        temp,
                        ensure_ascii=False,
                        indent=2,
                    )
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
        default: T,
        change: Callable[[T], R],
    ) -> R:
        """Выполнить чтение, изменение и запись под блокировкой"""
        with self._lock:
            current = self.read_json(settings_key, default)
            result = change(current)

            self.write_json(settings_key, current)

            return result
