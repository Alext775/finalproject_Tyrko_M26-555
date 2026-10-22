
"""Тесты логирования доменных операций"""

import unittest

from valutatrade_hub.decorators import log_action


class DecoratorTests(unittest.TestCase):
    """Проверки декоратора log_action"""

    def test_successful_action(self) -> None:
        """Проверить запись успешной операции"""

        @log_action("BUY")
        def operation(user_id: int, amount: float) -> dict[str, object]:
            """Выполнить тестовую покупку"""
            return {
                "rate": 60000.0,
                "amount": amount,
            }

        with self.assertLogs(
            "valutatrade.actions",
            level="INFO",
        ) as captured:
            result = operation(1, 0.01)

        self.assertEqual(result["rate"], 60000.0)
        self.assertIn(
            "result=OK",
            captured.output[0],
        )

    def test_failed_action(self) -> None:
        """Проверить запись ошибки без подавления исключения"""

        @log_action("SELL")
        def operation(user_id: int) -> None:
            """Выполнить тестовую продажу"""
            raise ValueError("Тестовая ошибка")

        with self.assertLogs(
            "valutatrade.actions",
            level="INFO",
        ) as captured:
            with self.assertRaisesRegex(
                ValueError,
                "Тестовая ошибка",
            ):
                operation(1)

        self.assertIn(
            "result=ERROR",
            captured.output[0],
        )
        self.assertIn(
            "ValueError",
            captured.output[0],
        )


if __name__ == "__main__":
    unittest.main()