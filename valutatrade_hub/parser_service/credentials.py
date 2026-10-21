"""Хранение и настройка API-ключей"""

import json
import os
import tempfile
from getpass import getpass
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CREDENTIALS_DIR = PROJECT_ROOT / ".secrets"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"

API_KEY_ENV_NAME = "EXCHANGERATE_API_KEY"


def load_api_key() -> str | None:
    """Загрузить API-ключ из окружения или файла"""
    environment_key = os.getenv(API_KEY_ENV_NAME, "").strip()

    if environment_key:
        return environment_key

    if not CREDENTIALS_FILE.exists():
        return None

    try:
        content = CREDENTIALS_FILE.read_text(encoding="utf-8")
        payload: object = json.loads(content)

    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    credentials = cast(dict[str, object], payload)
    key = credentials.get("exchangerate_api_key")

    if isinstance(key, str) and key.strip():
        return key.strip()

    return None


def save_api_key(key: str) -> None:
    """Сохранить API-ключ для следующих запусков"""
    key = key.strip()

    if not key or any(character.isspace() for character in key):
        raise ValueError("Некорректный API-ключ")

    CREDENTIALS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=CREDENTIALS_DIR,
            prefix="credentials-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temp_path = temporary.name

            json.dump(
                {"exchangerate_api_key": key},
                temporary,
                ensure_ascii=False,
                indent=2,
            )

            temporary.write("\n")

        os.chmod(temp_path, 0o600)
        os.replace(temp_path, CREDENTIALS_FILE)

    finally:
        if temp_path is not None and os.path.exists(temp_path):
            os.unlink(temp_path)


def configure_api_key(force: bool = False) -> bool:
    """Запросить API-ключ при необходимости"""
    if not force and load_api_key() is not None:
        return True

    print("\nДля фиатных валют требуется ключ ExchangeRate-API")
    print("Получить ключ: https://www.exchangerate-api.com/")

    try:
        key = getpass("Введите API-ключ (Enter для пропуска): ").strip()

    except (EOFError, KeyboardInterrupt):
        print("\nВвод ключа отменен")
        return False

    if not key:
        if load_api_key() is not None:
            print(
                "Ввод пропущен. Предыдущий API-ключ сохранен и продолжит использоваться"
            )
            return True

        print("API-ключ не задан. Будет доступен только CoinGecko")
        return False

    try:
        save_api_key(key)

    except (OSError, ValueError) as exc:
        print(f"Не удалось сохранить API-ключ: {exc}")
        return False

    print("API-ключ сохранен")

    if os.getenv(API_KEY_ENV_NAME):
        print(
            "Внимание: переменная окружения "
            "EXCHANGERATE_API_KEY имеет приоритет над файлом"
        )

    return True
