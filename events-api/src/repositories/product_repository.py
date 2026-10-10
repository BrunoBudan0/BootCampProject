from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from errors import DuplicatedBarcode
from models import EventCompany, Product


class ProductRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, product: Product) -> None:
        self.session.add(product)
        try:
            self.session.flush()
        except IntegrityError as error:
            self.session.rollback()
            if "uq_product_barcode" in str(error.orig):
                raise DuplicatedBarcode()
            raise

    def get_with_stand(self, product_id):
        query = (
            select(Product, EventCompany)
            .join(EventCompany, Product.event_company_id == EventCompany.id)
            .where(Product.id == product_id)
        )
        return self.session.execute(query).first()

    def search(self, filters: dict, include_inactive_of, limit: int, page: int):
        query = select(Product, EventCompany).join(
            EventCompany, Product.event_company_id == EventCompany.id
        )

        if filters.get("event_id"):
            query = query.where(EventCompany.event_id == filters["event_id"])
        if filters.get("event_company_id"):
            query = query.where(Product.event_company_id == filters["event_company_id"])
        if filters.get("barcode"):
            query = query.where(Product.barcode == filters["barcode"])
        if filters.get("name"):
            term = filters["name"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.where(Product.name.ilike(f"%{term}%", escape="\\"))

        if include_inactive_of is None:
            query = query.where(Product.active.is_(True))
        else:
            query = query.where(
                Product.active.is_(True) | (EventCompany.company_id == include_inactive_of)
            )

        query = (
            query.order_by(EventCompany.stand_name, Product.name, Product.id)
            .limit(limit + 1)
            .offset((page - 1) * limit)
        )
        rows = self.session.execute(query).all()
        return rows[:limit], len(rows) <= limit