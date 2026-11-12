import uuid

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import PRODUCT_SERVICE_URL
from app.models import Order


def create_order(db: Session, order_data):

    order_reference = f"ORD-{uuid.uuid4()}"

    reservation_id = None

    # Step 1: Reserve stock through Product Service
    try:
        response = httpx.post(
            f"{PRODUCT_SERVICE_URL}/products/{order_data.product_id}/reservations",
            json={
                "order_reference": order_reference,
                "quantity": order_data.quantity
            },
            timeout=10.0
        )

        if response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="Product not found"
            )

        if response.status_code == 409:
            raise HTTPException(
                status_code=409,
                detail="Insufficient stock"
            )

        response.raise_for_status()

        reservation = response.json()
        reservation_id = reservation["reservation_id"]

    except HTTPException:
        raise

    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="Product Service is unavailable"
        )

    except httpx.HTTPStatusError:
        raise HTTPException(
            status_code=502,
            detail="Product Service returned an unexpected error"
        )

    # Step 2: Calculate order amount
    unit_price = None

    try:
        product_response = httpx.get(
            f"{PRODUCT_SERVICE_URL}/products/{order_data.product_id}",
            timeout=10.0
        )
        product_response.raise_for_status()

        product = product_response.json()
        unit_price = float(product["price"])

        total_amount = unit_price * order_data.quantity

        # Step 3: Save order in Order Database
        new_order = Order(
            customer_id=order_data.customer_id,
            product_id=order_data.product_id,
            quantity=order_data.quantity,
            unit_price=unit_price,
            total_amount=total_amount,
            status="CREATED",
            reservation_id=reservation_id
        )

        db.add(new_order)
        db.commit()
        db.refresh(new_order)

        return new_order

    except Exception as error:

        db.rollback()

        # Step 4: Release reserved stock if order creation fails
        try:
            httpx.post(
                f"{PRODUCT_SERVICE_URL}/products/{order_data.product_id}/reservations/{reservation_id}/release",
                timeout=10.0
            )
        except httpx.RequestError:
            pass

        if isinstance(error, HTTPException):
            raise error

        raise HTTPException(
            status_code=500,
            detail="Order creation failed; inventory release was attempted"
        )
