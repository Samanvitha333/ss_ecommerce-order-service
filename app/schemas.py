from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict


class OrderCreate(BaseModel):
    customer_id: str = Field(min_length=1, max_length=100)
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: str
    product_id: int
    quantity: int
    unit_price: Decimal
    total_amount: Decimal
    status: str
    reservation_id: str
    created_at: datetime
    updated_at: datetime
