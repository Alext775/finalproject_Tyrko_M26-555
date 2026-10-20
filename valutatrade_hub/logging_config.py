"""Настройка логирования и ротации файлов"""

import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler

from valutatrade_hub.infra.settings import SettingsLoader

MAX_LOG_BYTES = 1_000_000
BACKUP_COUNT = 3


class IsoFormatter(logging.Formatter):
    """Форматирование времени в UTC ISO"""

    def formatTime(
        self,
        record: logging.LogRecord,
        datefmt: str | None = None,
    ) -> str:
        """Преобразовать timestamp"""
        return datetime.fromtimestamp(
            record.created,
            UTC,
        ).isoformat()


def configure_logging() -> None:
    """Создать журналы действий и парсера"""
    settings = SettingsLoader()
    logs_dir = settings.get("logs_dir")
    logs_dir.mkdir(parents=True, exist_ok=True)

    for name, filename in (
        ("valutatrade.actions", "actions.log"),
        ("valutatrade.parser", "parser.log"),
    ):
        logger = logging.getLogger(name)
        logger.setLevel(settings.get("log_level", "INFO"))
        logger.propagate = False

        if any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
            continue

        handler = RotatingFileHandler(
            logs_dir / filename,
            maxBytes=MAX_LOG_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )

        handler.setFormatter(IsoFormatter("%(levelname)s %(asctime)s %(message)s"))

        logger.addHandler(handler)
