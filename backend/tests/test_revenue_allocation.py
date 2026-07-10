import unittest

from backend.app.models import Drug, Payment, PrescriptionItem, Visit
from backend.app.services.revenue import allocate_payment_revenue


class RevenueAllocationTestCase(unittest.TestCase):
    def _items(self):
        definitions = [
            (1, 10, 4),
            (2, 5, 0),
            (3, 5, 2),
        ]
        items = []
        for drug_type, amount, cost in definitions:
            drug = Drug(type=drug_type)
            item = PrescriptionItem(amount=amount, new_amount=amount, purchase_cost=cost)
            item.drug = drug
            items.append(item)
        return items

    def test_explicit_discount_reconciles_to_payment(self):
        visit = Visit(consultation_fee=5)
        payment = Payment(
            amount=10,
            actual_consultation_fee=2,
            actual_drug_amount=8,
        )
        result = allocate_payment_revenue(payment, visit, self._items())

        self.assertEqual(result["consultation"], 2.0)
        self.assertEqual(result["drug"], 4.0)
        self.assertEqual(result["service"], 2.0)
        self.assertEqual(result["consumable"], 2.0)
        self.assertAlmostEqual(
            result["consultation"] + result["drug"] + result["service"] + result["consumable"],
            result["total"],
            places=6,
        )
        self.assertEqual(result["cost"], 6.0)
        self.assertEqual(result["profit"], 4.0)

    def test_legacy_discount_is_allocated_proportionally(self):
        visit = Visit(consultation_fee=5)
        payment = Payment(amount=10)
        result = allocate_payment_revenue(payment, visit, self._items())

        self.assertEqual(result["consultation"], 2.0)
        self.assertEqual(result["drug"], 4.0)
        self.assertEqual(result["service"], 2.0)
        self.assertEqual(result["consumable"], 2.0)


if __name__ == "__main__":
    unittest.main()
