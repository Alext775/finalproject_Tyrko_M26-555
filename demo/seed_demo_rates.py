"""Создать учебные курсы валют для демонстрации"""

from valutatrade_hub.core.utils import to_utc_iso
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.parser_service.storage import RateEntry, RateSnapshot

DEMO_RATES: dict[str, float] = {
    "BTC_USD": 60000.0,
    "ETH_USD": 3500.0,
    "SOL_USD": 150.0,
    "EUR_USD": 1.1,
    "GBP_USD": 1.3,
    "RUB_USD": 0.012,
}


def main() -> None:
    """Сохранить свежие учебные курсы в JSON"""
    timestamp = to_utc_iso()

    pairs: dict[str, RateEntry] = {
        pair: {
            "rate": rate,
            "updated_at": timestamp,
            "source": "Demo (not live)",
        }
        for pair, rate in DEMO_RATES.items()
    }

    snapshot: RateSnapshot = {
        "pairs": pairs,
        "last_refresh": timestamp,
    }

    DatabaseManager().write_json(
        "rates_file",
        snapshot,
    )

    print("Добавлены учебные курсы в data/rates.json (не реальные)")


if __name__ == "__main__":
    main()
