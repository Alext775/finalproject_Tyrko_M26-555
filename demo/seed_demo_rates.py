"""Создать учебные курсы валют для демонстрации"""

from valutatrade_hub.core.utils import to_utc_iso
from valutatrade_hub.infra.database import DatabaseManager

DEMO_RATES = {
    "BTC_USD": 60000.0,
    "ETH_USD": 3500.0,
    "SOL_USD": 150.0,
    "EUR_USD": 1.1,
    "GBP_USD": 1.3,
    "RUB_USD": 0.012,
}


def main() -> None:
    """Сохранить свежие курсы в JSON"""
    timestamp = to_utc_iso()

    DatabaseManager().write_json(
        "rates_file",
        {
            "pairs": {
                pair: {
                    "rate": rate,
                    "updated_at": timestamp,
                    "source": "Demo (not live)",
                }
                for pair, rate in DEMO_RATES.items()
            },
            "last_refresh": timestamp,
        },
    )

    print(
        "Добавлены учебные курсы "
        "в data/rates.json (не реальные)."
    )


if __name__ == "__main__":
    main()