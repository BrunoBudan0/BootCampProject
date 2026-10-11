import uuid
from dataclasses import dataclass

from models.enums import TransactionType

BPS = 10_000


@dataclass(frozen=True)
class CartLine:
    product_id: uuid.UUID
    quantity: int


@dataclass(frozen=True)
class PricedLine:
    product_id: uuid.UUID
    product_name: str
    unit_price_cents: int
    quantity: int

    @property
    def subtotal_cents(self) -> int:
        return self.unit_price_cents * self.quantity


@dataclass(frozen=True)
class PurchaseAmounts:
    total_cents: int
    fee_cents: int
    cashback_cents: int

    @property
    def buyer_pays_cents(self) -> int:
        return self.total_cents - self.cashback_cents

    @property
    def stand_receives_cents(self) -> int:
        return self.total_cents - self.fee_cents

    @property
    def event_keeps_cents(self) -> int:
        return self.fee_cents - self.cashback_cents


def normalize_cart(items: list[dict]) -> list[CartLine]:
    # mesmo produto duas vezes vira uma linha só; ordem fixa por id
    quantities: dict[uuid.UUID, int] = {}
    for item in items:
        product_id = uuid.UUID(str(item["product_id"]))
        quantities[product_id] = quantities.get(product_id, 0) + item["quantity"]

    return [CartLine(product_id, quantities[product_id]) for product_id in sorted(quantities)]


def percent_of(amount_cents: int, rate_bps: int) -> int:
    # sempre para baixo, só com inteiros
    return amount_cents * rate_bps // BPS


def calculate(lines: list[PricedLine], fee_rate_bps: int, cashback_rate_bps: int) -> PurchaseAmounts:
    if not lines:
        raise ValueError("carrinho vazio")
    if not 0 <= cashback_rate_bps <= fee_rate_bps <= BPS:
        raise ValueError("taxas fora da regra cashback <= tarifa <= 100%")

    total = sum(line.subtotal_cents for line in lines)

    return PurchaseAmounts(
        total_cents=total,
        fee_cents=percent_of(total, fee_rate_bps),
        cashback_cents=percent_of(total, cashback_rate_bps),
    )


@dataclass(frozen=True)
class Leg:
    type: str
    source_account_id: uuid.UUID
    destination_account_id: uuid.UUID
    amount_cents: int


def purchase_legs(amounts: PurchaseAmounts, buyer_account, stand_account, fee_account) -> list[Leg]:
    # a ordem importa: o stand recebe antes de repassar a tarifa,
    # e a conta fee recebe a tarifa antes de pagar o cashback
    legs = [
        Leg(TransactionType.PURCHASE.value, buyer_account, stand_account, amounts.total_cents),
        Leg(TransactionType.FEE.value, stand_account, fee_account, amounts.fee_cents),
        Leg(TransactionType.CASHBACK.value, fee_account, buyer_account, amounts.cashback_cents),
    ]
    # Pagamentos recusa valor zero, e perna de zero não move nada
    return [leg for leg in legs if leg.amount_cents > 0]
