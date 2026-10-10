from fastapi import Body, Request, status
from fastapi.responses import JSONResponse

from controllers import ProductController
from utils.caller import get_caller, parse_uuid
from utils.schema_handler import SchemaHandler


class ProductResource:
    @SchemaHandler.validate("create_product.json")
    def on_post(self, request: Request, payload: dict = Body(...)) -> JSONResponse:
        user_id, user_type = get_caller(request)
        parse_uuid(payload["event_company_id"], "event_company_id")
        body = ProductController().create_product(user_id, user_type, payload)
        return JSONResponse(content=body, status_code=status.HTTP_201_CREATED)

    @SchemaHandler.validate_query_params("search_products.json")
    def on_get_list(self, request: Request) -> JSONResponse:
        user_id, user_type = get_caller(request)
        params = request.query_params

        filters = {
            "event_id": parse_uuid(params["event_id"], "event_id") if "event_id" in params else None,
            "event_company_id": parse_uuid(params["event_company_id"], "event_company_id") if "event_company_id" in params else None,
            "barcode": params.get("barcode"),
            "name": params.get("name"),
        }
        limit = int(params.get("limit", 20))
        page = int(params.get("page", 1))

        body = ProductController().search_products(user_id, user_type, filters, limit, page)
        return JSONResponse(content=body, status_code=status.HTTP_200_OK)

    def on_get(self, request: Request, product_id: str) -> JSONResponse:
        get_caller(request)
        body = ProductController().get_product(parse_uuid(product_id, "id"))
        return JSONResponse(content=body, status_code=status.HTTP_200_OK)

    @SchemaHandler.validate("update_product.json")
    def on_put(self, request: Request, product_id: str, payload: dict = Body(...)) -> JSONResponse:
        user_id, user_type = get_caller(request)
        body = ProductController().update_product(
            user_id, user_type, parse_uuid(product_id, "id"), payload
        )
        return JSONResponse(content=body, status_code=status.HTTP_200_OK)