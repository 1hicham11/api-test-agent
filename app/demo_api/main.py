"""Demo Bookshop API — a small target API with INTENTIONAL bugs.

Run it, then point the agent at ``http://127.0.0.1:8001/openapi.json`` to see
the full workflow find real problems. The planted bugs:

1. ``GET /orders/{order_id}`` — missing error handling: an unknown order id
   raises instead of returning the documented 404, so clients get an
   **undocumented 500**.
2. ``GET /products/{product_id}`` — **schema mismatch**: the response bypasses
   the declared model and returns ``price`` as a string while omitting the
   required ``in_stock`` field.
3. ``GET /products`` — **suspiciously slow**: an artificial 1.5 s delay.

Everything else behaves correctly.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(
    title="Demo Bookshop API",
    description="A small demo API with intentional bugs for the API Test Agent.",
    version="1.0.0",
)


class Product(BaseModel):
    """A product in the catalog."""

    id: int
    name: str
    price: float
    category: Literal["fiction", "non-fiction", "science"]
    in_stock: bool


class NewProduct(BaseModel):
    """Payload for creating a product."""

    name: str = Field(min_length=1, max_length=100)
    price: float = Field(gt=0)
    category: Literal["fiction", "non-fiction", "science"]


class Order(BaseModel):
    """A placed order."""

    id: int
    product_id: int
    quantity: int
    total: float


class NewOrder(BaseModel):
    """Payload for placing an order."""

    product_id: int
    quantity: int = Field(ge=1, le=100)


PRODUCTS: dict[int, Product] = {
    1: Product(id=1, name="Dune", price=12.99, category="fiction", in_stock=True),
    2: Product(id=2, name="Cosmos", price=18.50, category="science", in_stock=True),
    3: Product(id=3, name="Sapiens", price=15.00, category="non-fiction", in_stock=False),
}
ORDERS: dict[int, Order] = {
    1: Order(id=1, product_id=1, quantity=2, total=25.98),
}


@app.get("/products", response_model=list[Product])
async def list_products(limit: int = 10) -> list[Product]:
    """List products. BUG: artificially slow (~1.5 s)."""
    await asyncio.sleep(1.5)
    return list(PRODUCTS.values())[:limit]


@app.get(
    "/products/{product_id}",
    response_model=Product,
    responses={404: {"description": "Product not found"}},
)
async def get_product(product_id: int) -> JSONResponse:
    """Get one product. BUG: response does not match the declared schema."""
    product = PRODUCTS.get(product_id)
    if product is None:
        raise HTTPException(404, "Product not found")
    # Intentional schema mismatch: price becomes a string, in_stock disappears.
    return JSONResponse(
        {
            "id": product.id,
            "name": product.name,
            "price": f"{product.price:.2f}",
            "category": product.category,
        }
    )


@app.post("/products", response_model=Product, status_code=201)
async def create_product(payload: NewProduct) -> Product:
    """Create a product (behaves correctly)."""
    product_id = max(PRODUCTS) + 1
    product = Product(id=product_id, in_stock=True, **payload.model_dump())
    PRODUCTS[product_id] = product
    return product


@app.get(
    "/orders/{order_id}",
    response_model=Order,
    responses={404: {"description": "Order not found"}},
)
async def get_order(order_id: int) -> Order:
    """Get one order. BUG: unknown ids raise → undocumented 500 instead of 404."""
    return ORDERS[order_id]  # KeyError on unknown id — the missing 404 check.


@app.post(
    "/orders",
    response_model=Order,
    status_code=201,
    responses={404: {"description": "Product not found"}},
)
async def create_order(payload: NewOrder) -> Order:
    """Place an order (behaves correctly)."""
    product = PRODUCTS.get(payload.product_id)
    if product is None:
        raise HTTPException(404, "Product not found")
    order_id = max(ORDERS) + 1
    order = Order(
        id=order_id,
        product_id=payload.product_id,
        quantity=payload.quantity,
        total=round(product.price * payload.quantity, 2),
    )
    ORDERS[order_id] = order
    return order


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe (behaves correctly)."""
    return {"status": "ok"}
