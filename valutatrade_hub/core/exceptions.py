"""Пользовательские исключения"""


class InsufficientFundsError(ValueError):
    """Недостаточно денег на балансе"""

    def __init__(self, available: float, required: float, code: str):
        self.available = available
        self.required = required
        self.code = code

        super().__init__(
            f"Недостаточно средств: доступно {available:.4f} {code}, "
            f"требуется {required:.4f} {code}"
        )


class CurrencyNotFoundError(ValueError):
    """Валюта не найдена"""

    def __init__(self, code: str):
        self.code = code
        super().__init__(f"Неизвестная валюта '{code}'")


class ApiRequestError(RuntimeError):
    """Ошибка при получении курсов валют"""

    def __init__(self, reason: str):
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")
