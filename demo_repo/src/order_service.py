"""
E-commerce Order Service
Demo codebase for CodeGuard AI regression testing demo.
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Product:
    id: str
    name: str
    price: float
    stock: int
    category: str = "general"


@dataclass
class CartItem:
    product: Product
    quantity: int

    @property
    def subtotal(self) -> float:
        return self.product.price * self.quantity


@dataclass
class Order:
    id: str
    user_id: str
    items: list[CartItem] = field(default_factory=list)
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    discount_code: Optional[str] = None

    def total(self) -> float:
        return sum(item.subtotal for item in self.items)


class InventoryError(Exception):
    pass


class OrderService:
    def __init__(self):
        self._inventory: dict[str, Product] = {}
        self._orders: dict[str, Order] = {}

    def add_product(self, product: Product):
        self._inventory[product.id] = product

    def get_product(self, product_id: str) -> Optional[Product]:
        return self._inventory.get(product_id)

    def check_stock(self, product_id: str, quantity: int) -> bool:
        """Check if enough stock is available for a product."""
        product = self._inventory.get(product_id)
        if not product:
            raise InventoryError(f"Product {product_id} not found")
        return product.stock >= quantity

    def create_order(self, user_id: str, cart: list[dict]) -> Order:
        """
        Create an order from a cart.
        cart = [{"product_id": str, "quantity": int}, ...]
        Raises InventoryError if stock is insufficient.
        """
        if not cart:
            raise ValueError("Cart cannot be empty")

        order = Order(id=f"ORD-{len(self._orders)+1:04d}", user_id=user_id)

        for entry in cart:
            product_id = entry["product_id"]
            quantity = entry["quantity"]

            if quantity <= 0:
                raise ValueError(f"Quantity must be positive, got {quantity}")

            if not self.check_stock(product_id, quantity):
                product = self._inventory[product_id]
                raise InventoryError(
                    f"Insufficient stock for {product.name}: "
                    f"requested {quantity}, available {product.stock}"
                )

            product = self._inventory[product_id]
            order.items.append(CartItem(product=product, quantity=quantity))
            product.stock -= quantity

        self._orders[order.id] = order
        return order

    def apply_discount(self, order_id: str, code: str) -> float:
        """Apply a discount code to an order. Returns new total."""
        order = self._orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        DISCOUNTS = {
            "SAVE10": 0.10,
            "SAVE20": 0.20,
            "FLIPKART50": 0.50,
        }
        rate = DISCOUNTS.get(code.upper())
        if not rate:
            raise ValueError(f"Invalid discount code: {code}")

        order.discount_code = code.upper()
        return order.total() * (1 - rate)

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order and restore inventory."""
        order = self._orders.get(order_id)
        if not order:
            return False
        if order.status == "shipped":
            raise ValueError("Cannot cancel a shipped order")

        # Restore stock
        for item in order.items:
            item.product.stock += item.quantity

        order.status = "cancelled"
        return True

    def get_order_summary(self, order_id: str) -> dict:
        """Return a summary dict for an order."""
        order = self._orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return {
            "id": order.id,
            "user_id": order.user_id,
            "status": order.status,
            "items": len(order.items),
            "total": round(order.total(), 2),
            "discount_code": order.discount_code,
        }
