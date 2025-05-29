from typing import List, Union
from uuid import UUID
from database import get_db
from dependencies import get_current_user
from fastapi import APIRouter, Depends, HTTPException
from kafka.producer import produce_order_event
from crud import (cancel_order, create_order, get_instrument, get_order, get_orders)
from models import (CreateOrderResponse, LimitOrder, LimitOrderBody, MarketOrder, MarketOrderBody)
from sqlalchemy.orm import Session

router = APIRouter()

@router.get(
    "/order",
    response_model=List[Union[LimitOrder, MarketOrder]],
    summary="List Orders",
)
def list_orders(user=Depends(get_current_user), db: Session = Depends(get_db)):
    db_orders = get_orders(db, user.id)
    result = []

    for o in db_orders:
        if o.type == "LIMIT":
            result.append(
                LimitOrder(
                    id=o.id,
                    status=o.status,
                    user_id=o.user_id,
                    timestamp=o.created_at,
                    body=LimitOrderBody(
                        direction=o.direction,
                        ticker=o.instrument_ticker,
                        qty=o.quantity,
                        price=o.price,
                    ),
                    filled=o.filled,
                )
            )
        else:
            result.append(
                MarketOrder(
                    id=o.id,
                    status=o.status,
                    user_id=o.user_id,
                    timestamp=o.created_at,
                    body=MarketOrderBody(
                        direction=o.direction,
                        ticker=o.instrument_ticker,
                        qty=o.quantity,
                    ),
                )
            )

    return result


@router.post(
    "/order",
    response_model=CreateOrderResponse,
    summary="Create Order",
)
async def create_order_endpoint(
    order: Union[LimitOrderBody, MarketOrderBody],
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    instrument = get_instrument(db, order.ticker)
    if not instrument:
        raise HTTPException(status_code=422, detail=f"Неправильный тикер: {order.ticker}")

    if isinstance(order, LimitOrderBody):
        if order.price <= 0:
            raise HTTPException(
                status_code=422, detail="Цена должна быть больше нуля."
            )

    db_order = create_order(db, order, user.id)
    db.refresh(db_order)

    await produce_order_event(db_order, "PLACED")

    return CreateOrderResponse(order_id=db_order.id)


@router.get(
    "/order/{order_id}",
    response_model=Union[LimitOrder, MarketOrder],
    summary="Get Order",
)
def get_order_endpoint(
    order_id: UUID, user=Depends(get_current_user), db: Session = Depends(get_db)
):
    db_order = get_order(db, order_id)
    if not db_order or (db_order.user_id != user.id and user.role != "ADMIN"):
        raise HTTPException(status_code=404, detail="Ордер не найден")

    if db_order.type == "LIMIT":
        return LimitOrder(
            id=db_order.id,
            status=db_order.status,
            user_id=db_order.user_id,
            timestamp=db_order.created_at,
            body=LimitOrderBody(
                direction=db_order.direction,
                ticker=db_order.instrument_ticker,
                qty=db_order.quantity,
                price=db_order.price,
            ),
            filled=db_order.filled,
        )
    else:
        return MarketOrder(
            id=db_order.id,
            status=db_order.status,
            user_id=db_order.user_id,
            timestamp=db_order.created_at,
            body=MarketOrderBody(
                direction=db_order.direction,
                ticker=db_order.instrument_ticker,
                qty=db_order.quantity,
            ),
        )


@router.delete("/order/{order_id}", response_model=dict, summary="Отмена ордера")
async def cancel_order_endpoint(
    order_id: UUID, user=Depends(get_current_user), db: Session = Depends(get_db)
):
    db_order = get_order(db, order_id)

    if not db_order or db_order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Ордер не найден")

    if db_order.status == "CANCELLED":
        raise HTTPException(status_code=422, detail="Ордер уже отменен")


    db.refresh(db_order)
    await produce_order_event(db_order, "CANCELLED")

    return {"success": True}