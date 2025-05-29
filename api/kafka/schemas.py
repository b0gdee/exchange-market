from enum import Enum
from uuid import UUID
from typing import Optional
from datetime import datetime
from pydantic import BaseModel

class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"

class OrderStatus(str, Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    CANCELED = "canceled"
    REJECTED = "rejected"

class PlaceOrderPayload(BaseModel):
    order_id: UUID
    user_id: UUID
    instrument: str
    type: OrderType
    price: Optional[float] = None
    quantity: int
    timestamp: datetime

class CancelOrderPayload(BaseModel):
    order_id: UUID
    user_id: UUID
    timestamp: datetime

class OrderStatusPayload(BaseModel):
    order_id: UUID
    status: OrderStatus
    timestamp: datetime

class TradeUpdatePayload(BaseModel):
    trade_id: UUID
    buyer_id: Optional[UUID] = None
    seller_id: Optional[UUID] = None
    instrument: str
    price: float
    quantity: int
    timestamp: datetime