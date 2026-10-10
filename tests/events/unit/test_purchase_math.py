import uuid
import pytest
from utils.purchase_math import CartLine, PricedLine, calculate, normalize_cart, percent_of

def line(price, quantity=1, name="Livro"):
    return PricedLine(uuid.uuid4(), name, price, quantity)
class TestNormalizeCart:
    def test_same_product_twice_becomes_one_line(self):
        product = uuid.uuid4()
        cart = normalize_cart([
            {"product_id": str(product), "quantity": 2},
            {"product_id": str(product), "quantity": 3},
        ])

        assert cart == [CartLine(product, 5)]

    def test_lines_come_in_a_fixed_order(self):
        a, b, c = sorted(uuid.uuid4() for _ in range(3))
        cart = normalize_cart([
            {"product_id": str(c), "quantity": 1},
            {"product_id": str(a), "quantity": 1},
            {"product_id": str(b), "quantity": 1},
        ])

        assert [line.product_id for line in cart] == [a, b, c]
class TestCalculate:
    def test_example_from_the_rfc(self):
        # R$ 40,00 com tarifa de 5% e cashback de 2%
        amounts = calculate([line(4000)], fee_rate_bps=500, cashback_rate_bps=200)

        assert amounts.total_cents == 4000
        assert amounts.fee_cents == 200
        assert amounts.cashback_cents == 80
        assert amounts.buyer_pays_cents == 3920
        assert amounts.stand_receives_cents == 3800
        assert amounts.event_keeps_cents == 120

    def test_total_sums_every_line(self):
        amounts = calculate([line(1500, 2), line(990, 3)], fee_rate_bps=0, cashback_rate_bps=0)

        assert amounts.total_cents == 1500 * 2 + 990 * 3

    def test_fractions_of_a_cent_go_down(self):
        # 5% de 1,99 = 9,95 centavos -> 9; 2% = 3,98 -> 3
        amounts = calculate([line(199)], fee_rate_bps=500, cashback_rate_bps=200)

        assert amounts.fee_cents == 9
        assert amounts.cashback_cents == 3

    def test_small_purchase_can_have_zero_fee(self):
        amounts = calculate([line(1)], fee_rate_bps=500, cashback_rate_bps=200)

        assert amounts.fee_cents == 0
        assert amounts.cashback_cents == 0

    def test_cashback_never_above_fee_never_above_total(self):
        for total in range(1, 5000, 7):
            for fee_bps, cashback_bps in [(500, 200), (500, 500), (10000, 9999), (1, 0), (333, 111)]:
                amounts = calculate([line(total)], fee_bps, cashback_bps)
                assert 0 <= amounts.cashback_cents <= amounts.fee_cents <= amounts.total_cents

    def test_money_is_conserved(self):
        amounts = calculate([line(12345, 7)], fee_rate_bps=750, cashback_rate_bps=125)

        moved = amounts.stand_receives_cents + amounts.event_keeps_cents + amounts.cashback_cents
        assert moved == amounts.total_cents

    def test_large_values_stay_exact(self):
        amounts = calculate([line(999_999_999, 999)], fee_rate_bps=499, cashback_rate_bps=101)

        assert amounts.total_cents == 999_999_999 * 999
        assert amounts.fee_cents == 999_999_999 * 999 * 499 // 10_000

    def test_empty_cart_is_refused(self):
        with pytest.raises(ValueError):
            calculate([], fee_rate_bps=500, cashback_rate_bps=200)

    def test_cashback_above_fee_is_refused(self):
        with pytest.raises(ValueError):
            calculate([line(100)], fee_rate_bps=200, cashback_rate_bps=500)


def test_percent_of_uses_only_integers():
    assert percent_of(10, 3333) == 3
    assert isinstance(percent_of(10, 3333), int)