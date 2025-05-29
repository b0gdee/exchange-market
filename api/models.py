from datetime import datetime
from enum import Enum
from typing import List, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    NEW = "NEW"
    EXECUTED = "EXECUTED"
    PARTIALLY_EXECUTED = "PARTIALLY_EXECUTED"
    CANCELLED = "CANCELLED"


class UserRole(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"


class NewUser(BaseModel):
    name: str = Field(..., min_length=3)


class User(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    role: UserRole
    api_key: str


class Instrument(BaseModel):
    name: str
    ticker: str = Field(..., pattern="^[A-Z]{2,10}$")


class Level(BaseModel):
    price: int
    qty: int


class L2OrderBook(BaseModel):
    bid_levels: List[Level]
    ask_levels: List[Level]


class Transaction(BaseModel):
    ticker: str
    amount: int
    price: int
    timestamp: datetime


class LimitOrderBody(BaseModel):
    direction: Direction
    ticker: str
    qty: int = Field(..., gt=0)
    price: int = Field(..., gt=0)


class MarketOrderBody(BaseModel):
    direction: Direction
    ticker: str
    qty: int = Field(..., gt=0)


class LimitOrder(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    status: OrderStatus
    user_id: UUID
    timestamp: datetime
    body: LimitOrderBody
    filled: int = 0


class MarketOrder(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    status: OrderStatus
    user_id: UUID
    timestamp: datetime
    body: MarketOrderBody


class CreateOrderResponse(BaseModel):
    success: bool = True
    order_id: UUID


class Ok(BaseModel):
    success: Literal[True] = True


class DepositRequest(BaseModel):
    user_id: UUID
    ticker: str
    amount: int = Field(..., gt=0)


class WithdrawRequest(BaseModel):
    user_id: UUID
    ticker: str
    amount: int = Field(..., gt=0)


class InstrumentCreate(BaseModel):
    ticker: str
    name: str


class InstrumentOut(BaseModel):
    ticker: str
    name: str

    class Config:
        orm_mode = True