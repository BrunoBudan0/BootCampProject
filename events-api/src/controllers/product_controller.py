import uuid

from controllers.base_controller import BaseController
from dtos import product_to_dict
from errors import EventNotFound, NonPositiveAmount, NotAllowedForUserType, ProductNotFound, StockChanged
from models import Product, UserType
from repositories import EventCompanyRepository, ProductRepository


class ProductController(BaseController):
    def __init__(self) -> None:
        super().__init__(self.__class__.__name__)
        self.products = ProductRepository(self.session)
        self.stands = EventCompanyRepository(self.session)

    def create_product(self, user_id: uuid.UUID, user_type: str, payload: dict) -> dict:
        if user_type != UserType.COMPANY.value:
            raise NotAllowedForUserType()

        stand = self.stands.get_by_id(uuid.UUID(payload["event_company_id"]))
        if stand is None or stand.company_id != user_id:
            raise EventNotFound()

        product = Product(
            event_company_id=stand.id,
            name=payload["name"],
            barcode=payload["barcode"],
            price_cents=payload["price_cents"],
            stock=payload.get("stock"),
        )
        self.products.add(product)
        self.session.commit()

        return product_to_dict(product, stand)

    def search_products(self, user_id: uuid.UUID, user_type: str, filters: dict, limit: int, page: int) -> dict:
        owner = user_id if user_type == UserType.COMPANY.value else None
        rows, is_last_page = self.products.search(filters, owner, limit, page)
        return {
            "data": [product_to_dict(product, stand) for product, stand in rows],
            "is_last_page": is_last_page,
        }

    def get_product(self, product_id: uuid.UUID) -> dict:
        row = self.products.get_with_stand(product_id)
        if row is None:
            raise ProductNotFound()

        product, stand = row
        return product_to_dict(product, stand)

    def update_product(self, user_id: uuid.UUID, user_type: str, product_id: uuid.UUID, payload: dict) -> dict:
        row = self.products.get_with_stand(product_id)
        if row is None:
            raise ProductNotFound()

        product, stand = row
        if user_type != UserType.COMPANY.value or stand.company_id != user_id:
            raise ProductNotFound()

        if "price_cents" in payload and payload["price_cents"] <= 0:
            raise NonPositiveAmount()

        if "stock" in payload:
            if not self.products.set_stock(product.id, payload["expected_stock"], payload["stock"]):
                raise StockChanged()

        for field in ("name", "price_cents", "active"):
            if field in payload:
                setattr(product, field, payload[field])

        self.session.commit()
        return product_to_dict(product, stand)
