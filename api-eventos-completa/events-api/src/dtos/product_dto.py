from models import EventCompany, Product


def product_to_dict(product: Product, stand: EventCompany) -> dict:
    return {
        "id": str(product.id),
        "event_id": str(stand.event_id),
        "event_company_id": str(product.event_company_id),
        "stand_name": stand.stand_name,
        "name": product.name,
        "barcode": product.barcode,
        "price_cents": product.price_cents,
        "stock": product.stock,
        "active": product.active,
    }
