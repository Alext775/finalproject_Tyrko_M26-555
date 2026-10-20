"""Хранение кеша и истории валютных курсов"""

from valutatrade_hub.core.utils import parse_utc_iso
from valutatrade_hub.infra.database import DatabaseManager


class RatesStorage:
    """Сохранение актуальных и исторических курсов"""

    def __init__(
        self,
        database: DatabaseManager | None = None,
    ) -> None:
        self.db = database or DatabaseManager()

    def save_rates(
        self,
        updates: dict[str, dict],
        timestamp: str,
    ) -> int:
        """Сохранить новые курсы без дубликатов"""
        accepted: dict[str, dict] = {}

        with self.db.transaction_lock:

            def update_snapshot(snapshot: dict) -> None:
                pairs = snapshot.setdefault("pairs", {})

                for pair, entry in updates.items():
                    previous = pairs.get(pair)

                    if previous and (
                        parse_utc_iso(previous["updated_at"])
                        >= parse_utc_iso(entry["updated_at"])
                    ):
                        continue

                    pairs[pair] = entry
                    accepted[pair] = entry

                if accepted:
                    snapshot["last_refresh"] = timestamp

            self.db.update_json(
                "rates_file",
                {"pairs": {}, "last_refresh": None},
                update_snapshot,
            )

            if accepted:

                def append_history(history: list) -> None:
                    existing_ids = {
                        entry["id"]
                        for entry in history
                    }

                    for pair, entry in accepted.items():
                        from_code, to_code = pair.split(
                            "_",
                            maxsplit=1,
                        )

                        record_id = (
                            f"{pair}_{entry['updated_at']}"
                        )

                        if record_id not in existing_ids:
                            history.append({
                                "id": record_id,
                                "from_currency": from_code,
                                "to_currency": to_code,
                                "rate": entry["rate"],
                                "timestamp": entry["updated_at"],
                                "source": entry["source"],
                                "meta": {},
                            })

                            existing_ids.add(record_id)

                self.db.update_json(
                    "history_file",
                    [],
                    append_history,
                )

        return len(accepted)