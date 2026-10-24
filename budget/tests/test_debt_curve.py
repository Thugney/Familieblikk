from decimal import Decimal
from types import SimpleNamespace
from django.test import SimpleTestCase
from budget import services


class DebtCurveTests(SimpleTestCase):
    def debts(self):
        return [SimpleNamespace(pk='a', opening_ore=1000000, annual_rate=Decimal('6.0'), minimum_ore=50000),
                SimpleNamespace(pk='b', opening_ore=300000, annual_rate=Decimal('20.0'), minimum_ore=20000)]

    def test_curve_matches_the_projection_and_ends_at_zero(self):
        for strategy, extra in (('avalanche', 0), ('snowball', 25000)):
            with self.subTest(strategy=strategy):
                curve = services.debt_balance_curve(self.debts(), strategy, extra)
                projection = services.debt_projection(self.debts(), strategy, extra)
                self.assertEqual(curve[0], 1300000)
                self.assertEqual(curve[-1], 0)
                self.assertEqual(len(curve) - 1, projection['months'])
                self.assertTrue(all(a >= b for a, b in zip(curve, curve[1:])))

    def test_curve_is_empty_when_there_is_no_estimate(self):
        self.assertEqual(services.debt_balance_curve([]), [])
        self.assertEqual(services.debt_balance_curve([SimpleNamespace(pk='x', opening_ore=100, annual_rate=None, minimum_ore=0)]), [])
        self.assertEqual(services.debt_balance_curve([SimpleNamespace(pk='x', opening_ore=1000000, annual_rate=Decimal('0'), minimum_ore=0)]), [])
