from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Product, Purchase, PurchaseProduct
from utils.purchase_math import CartLine, PricedLine


class KeyAlreadyUsed(Exception):
    pass


class PurchaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_key(self, idempotency_key: str):
        return self.session.scalars(
            select(Purchase).where(Purchase.idempotency_key == idempotency_key)
        ).first()

    def items_of(self, purchase_id) -> list[PurchaseProduct]:
        query = (
            select(PurchaseProduct)
            .where(PurchaseProduct.purchase_id == purchase_id)
            .order_by(PurchaseProduct.product_id)
        )
        return list(self.session.scalars(query))

    def products_of_cart(self, cart: list[CartLine]) -> dict:
        ids = [line.product_id for line in cart]
        rows = self.session.scalars(select(Product).where(Product.id.in_(ids)))
        return {product.id: product for product in rows}

    def reserve(self, event_company_id, line: CartLine):
        # baixa só se tiver estoque; null = sem controle de estoque
        query = (
            update(Product)
            .where(
                Product.id == line.product_id,
                Product.event_company_id == event_company_id,
                Product.active.is_(True),
                Product.stock.is_(None) | (Product.stock >= line.quantity),
            )
            .values(stock=Product.stock - line.quantity)
            .returning(Product.name, Product.price_cents)
            .execution_options(synchronize_session=False)
        )
        row = self.session.execute(query).first()
        if row is None:
            return None
        return PricedLine(line.product_id, row.name, row.price_cents, line.quantity)

    def is_active(self, product_id) -> bool:
        return bool(self.session.scalar(select(Product.active).where(Product.id == product_id)))

    def add(self, purchase: Purchase, lines: list[PricedLine]) -> list[PurchaseProduct]:
        items = [
            PurchaseProduct(
                purchase_id=purchase.id,
                product_id=line.product_id,
                product_name=line.product_name,
                unit_price_cents=line.unit_price_cents,
                quantity=line.quantity,
            )
            for line in lines
        ]
        self.session.add(purchase)
        try:
            self.session.flush()
        except IntegrityError as error:
            self.session.rollback()
            if "uq_purchase_idempotency" in str(error.orig):
                raise KeyAlreadyUsed()
            raise

        self.session.add_all(items)
        self.session.flush()
        return items