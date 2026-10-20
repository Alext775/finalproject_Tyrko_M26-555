"""Хранение кеша и истории валютных курсов"""

from typing import TypedDict

from valutatrade_hub.core.utils import parse_utc_iso
from valutatrade_hub.infra.database import DatabaseManager


class RateEntry(TypedDict):
    """Курс валюты с метаданными"""

    rate: float
    updated_at: str
    source: str


class RateSnapshot(TypedDict):
    """Снимок актуальных курсов"""

    pairs: dict[str, RateEntry]
    last_refresh: str | None


class HistoryEntry(TypedDict):
    """Историческая запись курса"""

    id: str
    from_currency: str
    to_currency: str
    rate: float
    timestamp: str
    source: str
    meta: dict[str, object]


class RatesStorage:
    """Сохранение актуальных и исторических курсов"""

    def __init__(
        self,
        database: DatabaseManager | None = None,
    ) -> None:
        self.db = database if database is not None else DatabaseManager()

    def save_rates(
        self,
        updates: dict[str, RateEntry],
        timestamp: str,
    ) -> int:
        """Сохранить новые курсы без дубликатов"""
        accepted: dict[str, RateEntry] = {}

        with self.db.transaction_lock:
            default_snapshot: RateSnapshot = {
                "pairs": {},
                "last_refresh": None,
            }

            def update_snapshot(snapshot: RateSnapshot) -> None:
                """Обновить актуальные курсы"""
                pairs = snapshot["pairs"]

                for pair, entry in updates.items():
                    previous = pairs.get(pair)

                    if previous is not None:
                        previous_time = parse_utc_iso(previous["updated_at"])
                        new_time = parse_utc_iso(entry["updated_at"])

                        if previous_time >= new_time:
                            continue

                    pairs[pair] = entry
                    accepted[pair] = entry

                if accepted:
                    snapshot["last_refresh"] = timestamp

            self.db.update_json(
                "rates_file",
                default_snapshot,
                update_snapshot,
            )

            if accepted:
                default_history: list[HistoryEntry] = []

                def append_history(
                    history: list[HistoryEntry],
                ) -> None:
                    """Добавить новые измерения в историю"""
                    existing_ids = {entry["id"] for entry in history}

                    for pair, entry in accepted.items():
                        from_code, to_code = pair.split(
                            "_",
                            maxsplit=1,
                        )

                        record_id = f"{pair}_{entry['updated_at']}"

                        if record_id in existing_ids:
                            continue

                        history.append(
                            {
                                "id": record_id,
                                "from_currency": from_code,
                                "to_currency": to_code,
                                "rate": entry["rate"],
                                "timestamp": entry["updated_at"],
                                "source": entry["source"],
                                "meta": {},
                            }
                        )

                        existing_ids.add(record_id)

                self.db.update_json(
                    "history_file",
                    default_history,
                    append_history,
                )

        return len(accepted)
