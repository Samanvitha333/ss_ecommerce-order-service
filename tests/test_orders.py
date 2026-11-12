from unittest.mock import Mock

import httpx


def mock_response(status_code, json_data=None):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = json_data or {}
    response.raise_for_status.return_value = None
    return response


def mock_product_service(monkeypatch, product_id=1, price="799.00"):
    from app.services import order_service

    reservation_response = mock_response(
        201,
        {
            "reservation_id": "test-reservation-001",
            "order_reference": "ORD-TEST-001",
            "product_id": product_id,
            "quantity": 2,
            "status": "RESERVED"
        }
    )

    product_response = mock_response(
        200,
        {
            "id": product_id,
            "name": "Wireless Mouse",
            "price": price,
            "stock_quantity": 48
        }
    )

    monkeypatch.setattr(
        order_service.httpx,
        "post",
        lambda *args, **kwargs: reservation_response
    )

    monkeypatch.setattr(
        order_service.httpx,
        "get",
        lambda *args, **kwargs: product_response
    )


def test_create_order_success(client, monkeypatch):
    mock_product_service(monkeypatch)

    response = client.post(
        "/orders",
        json={
            "customer_id": "CUST-101",
            "product_id": 1,
            "quantity": 2
        }
    )

    assert response.status_code == 201

    data = response.json()

    assert data["customer_id"] == "CUST-101"
    assert data["product_id"] == 1
    assert data["quantity"] == 2
    assert data["unit_price"] == "799.00"
    assert data["total_amount"] == "1598.00"
    assert data["status"] == "CREATED"
    assert data["reservation_id"] == "test-reservation-001"


def test_get_order(client, monkeypatch):
    mock_product_service(monkeypatch)

    create_response = client.post(
        "/orders",
        json={
            "customer_id": "CUST-101",
            "product_id": 1,
            "quantity": 2
        }
    )

    order_id = create_response.json()["id"]

    response = client.get(f"/orders/{order_id}")

    assert response.status_code == 200
    assert response.json()["id"] == order_id
    assert response.json()["customer_id"] == "CUST-101"


def test_get_all_orders(client, monkeypatch):
    mock_product_service(monkeypatch)

    client.post(
        "/orders",
        json={
            "customer_id": "CUST-101",
            "product_id": 1,
            "quantity": 2
        }
    )

    response = client.get("/orders")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_insufficient_stock(client, monkeypatch):
    from app.services import order_service

    conflict_response = mock_response(
        409,
        {"detail": "Insufficient stock available"}
    )

    monkeypatch.setattr(
        order_service.httpx,
        "post",
        lambda *args, **kwargs: conflict_response
    )

    response = client.post(
        "/orders",
        json={
            "customer_id": "CUST-102",
            "product_id": 1,
            "quantity": 1000
        }
    )

    assert response.status_code == 409

    assert client.get("/orders").json() == []


def test_product_not_found(client, monkeypatch):
    from app.services import order_service

    not_found_response = mock_response(
        404,
        {"detail": "Product not found"}
    )

    monkeypatch.setattr(
        order_service.httpx,
        "post",
        lambda *args, **kwargs: not_found_response
    )

    response = client.post(
        "/orders",
        json={
            "customer_id": "CUST-103",
            "product_id": 9999,
            "quantity": 1
        }
    )

    assert response.status_code == 404

    assert client.get("/orders").json() == []


def test_product_service_unavailable(client, monkeypatch):
    from app.services import order_service

    def raise_connection_error(*args, **kwargs):
        request = httpx.Request(
            "POST",
            "http://localhost:8001/products/1/reservations"
        )
        raise httpx.ConnectError(
            "Connection failed",
            request=request
        )

    monkeypatch.setattr(
        order_service.httpx,
        "post",
        raise_connection_error
    )

    response = client.post(
        "/orders",
        json={
            "customer_id": "CUST-104",
            "product_id": 1,
            "quantity": 1
        }
    )

    assert response.status_code == 503

    assert client.get("/orders").json() == []


def test_order_persistence(client, monkeypatch):
    mock_product_service(monkeypatch)

    create_response = client.post(
        "/orders",
        json={
            "customer_id": "CUST-105",
            "product_id": 1,
            "quantity": 2
        }
    )

    order_id = create_response.json()["id"]

    # Retrieve the order again from the database.
    response = client.get(f"/orders/{order_id}")

    assert response.status_code == 200
    assert response.json()["id"] == order_id
    assert response.json()["customer_id"] == "CUST-105"

def test_release_stock_when_order_creation_fails(
    client, monkeypatch
):
    from app.services import order_service
    from sqlalchemy.orm import Session

    # Track Product Service POST requests
    post_calls = []

    # Mock successful inventory reservation
    reservation_response = mock_response(
        201,
        {
            "reservation_id": "test-reservation-002",
            "order_reference": "ORD-TEST-002",
            "product_id": 1,
            "quantity": 2,
            "status": "RESERVED"
        }
    )

    # Mock successful inventory release
    release_response = mock_response(
        200,
        {"status": "RELEASED"}
    )

    def mock_post(url, *args, **kwargs):
        post_calls.append(url)

        if url.endswith("/reservations"):
            return reservation_response

        if url.endswith("/release"):
            return release_response

        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(
        order_service.httpx,
        "post",
        mock_post
    )

    # Mock successful product details response
    monkeypatch.setattr(
        order_service.httpx,
        "get",
        lambda *args, **kwargs: mock_response(
            200,
            {
                "id": 1,
                "name": "Wireless Mouse",
                "price": "799.00"
            }
        )
    )

    # Simulate a database commit failure
    def failed_commit(self):
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(Session, "commit", failed_commit)

    response = client.post(
        "/orders",
        json={
            "customer_id": "CUST-106",
            "product_id": 1,
            "quantity": 2
        }
    )

    # Order creation should fail
    assert response.status_code == 500

    # Verify that inventory reservation was attempted
    assert any(
        url.endswith("/reservations")
        for url in post_calls
    )

    # Verify that inventory release was attempted
    assert any(
        url.endswith("/release")
        for url in post_calls
    )

    # Verify that no order was persisted
    assert client.get("/orders").json() == []    
