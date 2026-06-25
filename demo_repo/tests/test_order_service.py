"""
Existing tests for the order service.
These existed BEFORE the new changes - CodeGuard AI will detect which are at risk.
"""
import pytest
import sys
sys.path.insert(0, ".")

from demo_repo.src.order_service import OrderService, Product, InventoryError


@pytest.fixture
def service():
    svc = OrderService()
    svc.add_product(Product(id="P001", name="Phone", price=9999.0, stock=10))
    svc.add_product(Product(id="P002", name="Charger", price=499.0, stock=5))
    return svc


def test_create_order_basic(service):
    """Basic order creation should work."""
    order = service.create_order("user1", [{"product_id": "P001", "quantity": 1}])
    assert order.user_id == "user1"
    assert len(order.items) == 1
    assert order.total() == 9999.0


def test_create_order_reduces_stock(service):
    """Creating an order should reduce product stock."""
    service.create_order("user1", [{"product_id": "P001", "quantity": 3}])
    assert service.get_product("P001").stock == 7


def test_insufficient_stock_raises(service):
    """Should raise InventoryError when stock is insufficient."""
    with pytest.raises(InventoryError):
        service.create_order("user1", [{"product_id": "P002", "quantity": 99}])


def test_empty_cart_raises(service):
    """Empty cart should raise ValueError."""
    with pytest.raises(ValueError):
        service.create_order("user1", [])


def test_cancel_order_restores_stock(service):
    """Cancelling an order should restore stock."""
    order = service.create_order("user1", [{"product_id": "P001", "quantity": 2}])
    assert service.get_product("P001").stock == 8
    service.cancel_order(order.id)
    assert service.get_product("P001").stock == 10
