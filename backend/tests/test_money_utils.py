import unittest
from decimal import Decimal

from backend.app.utils.money import parse_nonnegative_money


class MoneyUtilsTestCase(unittest.TestCase):
    def test_rounds_half_up_to_cents(self):
        self.assertEqual(parse_nonnegative_money("1.005", "amount"), 1.01)
        self.assertEqual(parse_nonnegative_money("2.675", "amount"), 2.68)
        self.assertEqual(parse_nonnegative_money(Decimal("0.004"), "amount"), 0.0)
        self.assertEqual(parse_nonnegative_money(10, "amount"), 10.0)

    def test_rejects_invalid_values(self):
        for value in (True, False, -0.01, "abc", None, "Infinity", "NaN", "1e100000"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_nonnegative_money(value, "amount")


if __name__ == "__main__":
    unittest.main()
