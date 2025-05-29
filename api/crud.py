import uuid
from datetime import datetime
from typing import Union
from uuid import UUID

import models
import schemas
from fastapi import HTTPException, status
from schemas import Balance
from schemas import Instrument as ORMInstrument
from schemas import User
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def get_user(db: Session, user_id: UUID):
    return db.query(schemas.User).filter(schemas.User.id == user_id).first()


def get_user_by_api_key(db: Session, api_key: str):
    return db.query(schemas.User).filter(schemas.User.api_key == api_key).first()


def create_user(db: Session, user: models.NewUser):
    db_user = schemas.User(name=user.name, api_key=str(uuid.uuid4()))
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_instruments(db: Session, skip: int = 0, limit: int = 100):
    return (
        db.query(schemas.Instrument)
        .filter(schemas.Instrument.is_active == True)
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_instrument(db: Session, ticker: str):
    return (
        db.query(schemas.Instrument)
        .filter(schemas.Instrument.ticker == ticker)
        .first()
    )


def create_instrument(db: Session, instrument: models.Instrument):
    existing_instrument = (
        db.query(schemas.Instrument)
        .filter(schemas.Instrument.ticker == instrument.ticker)
        .first()
    )

    if existing_instrument:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Instrument with ticker {instrument.ticker} already exists",
        )

    db_instrument = schemas.Instrument(
        ticker=instrument.ticker, name=instrument.name
    )

    db.add(db_instrument)
    db.commit()
    db.refresh(db_instrument)
    return db_instrument


def delete_instrument(db: Session, ticker: str) -> bool:
    instrument = (
        db.query(schemas.Instrument)
        .filter(schemas.Instrument.ticker == ticker)
        .first()
    )
    if not instrument:
        return False
    db.delete(instrument)
    db.commit()
    return True


def get_orderbook(db: Session, ticker: str, limit: int = 10):
    bids = (
        db.query(schemas.Order)
        .filter(
            schemas.Order.instrument_ticker == ticker,
            schemas.Order.direction == "BUY",
            schemas.Order.status.in_(["NEW", "PARTIALLY_EXECUTED"]),
            schemas.Order.type == "LIMIT",
            schemas.Order.price != None,
        )
        .order_by(schemas.Order.price.desc())
        .limit(limit)
        .all()
    )

    asks = (
        db.query(schemas.Order)
        .filter(
            schemas.Order.instrument_ticker == ticker,
            schemas.Order.direction == "SELL",
            schemas.Order.status.in_(["NEW", "PARTIALLY_EXECUTED"]),
            schemas.Order.type == "LIMIT",
            schemas.Order.price != None,
        )
        .order_by(schemas.Order.price.asc())
        .limit(limit)
        .all()
    )

    return bids, asks


def get_transactions(db: Session, ticker: str, limit: int = 10):
    return (
        db.query(schemas.Transaction)
        .filter(schemas.Transaction.instrument_ticker == ticker)
        .order_by(schemas.Transaction.created_at.desc())
        .limit(limit)
        .all()
    )


def get_orders(db: Session, user_id: UUID):
    return db.query(schemas.Order).filter(schemas.Order.user_id == user_id).all()


def get_order(db: Session, order_id: UUID):
    return db.query(schemas.Order).filter(schemas.Order.id == order_id).first()


def create_order(
    db: Session,
    order: Union[models.LimitOrderBody, models.MarketOrderBody],
    user_id: UUID,
):
    instrument = get_instrument(db, order.ticker)

    if not instrument:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ticker"
        )

    if order.qty <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order quantity must be greater than zero",
        )

    if isinstance(order, models.LimitOrderBody) and order.price is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit order must include a price",
        )

    if order.direction == "SELL":
        user_balance = get_balance(db, user_id, order.ticker)
        required_amount = order.qty
        if not user_balance or user_balance.amount < required_amount:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Insufficient balance",
            )

    db_order = schemas.Order(
        user_id=user_id,
        instrument_ticker=order.ticker,
        direction=order.direction.value,
        type="LIMIT" if isinstance(order, models.LimitOrderBody) else "MARKET",
        price=order.price if isinstance(order, models.LimitOrderBody) else None,
        quantity=order.qty,
        status="NEW",
    )
    db.add(db_order)
    db.flush()

    match_order(db, db_order)

    db.commit()
    db.refresh(db_order)
    return db_order


def cancel_order(db: Session, order_id: UUID) -> bool:
    order = db.query(schemas.Order).filter(schemas.Order.id == order_id).first()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )

    if order.type == "MARKET":
        if order.status != "NEW" or order.filled > 0:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Cannot cancel market order (already executed or processing)",
            )
    else:
        if order.status not in ["NEW", "PARTIALLY_EXECUTED"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot cancel limit order (already executed, cancelled, or rejected)",
            )

    order.status = "CANCELLED"
    db.commit()
    return True


def get_balance(db: Session, user_id: UUID, ticker: str):
    return (
        db.query(schemas.Balance)
        .filter(
            schemas.Balance.user_id == user_id, schemas.Balance.ticker == ticker
        )
        .first()
    )


def get_balances(db: Session, user_id: UUID):
    return (
        db.query(schemas.Balance).filter(schemas.Balance.user_id == user_id).all()
    )


def update_balance(db: Session, user_id: UUID, ticker: str, amount: int):
    user = db.query(schemas.User).filter(schemas.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    balance = (
        db.query(schemas.Balance)
        .filter(
            schemas.Balance.user_id == user_id, schemas.Balance.ticker == ticker
        )
        .first()
    )

    if balance and (balance.amount + amount < 0):
        raise ValueError("Insufficient balance to deduct")

    if balance:
        balance.amount += amount
    else:
        balance = schemas.Balance(user_id=user_id, ticker=ticker, amount=amount)
        db.add(balance)

    db.commit()
    db.refresh(balance)
    return balance


def delete_user(db: Session, user_id: UUID):
    user = db.query(schemas.User).filter(schemas.User.id == user_id).first()
    if user:
        db.delete(user)
        db.commit()
        return True
    return False

def match_order(db: Session, new_order: schemas.Order):
    is_market_order = new_order.type == "MARKET"
    opposite_side = "BUY" if new_order.direction == "SELL" else "SELL"

    with db.begin_nested():
        base_query = db.query(schemas.Order).filter(
            schemas.Order.instrument_ticker == new_order.instrument_ticker,
            schemas.Order.direction == opposite_side,
            schemas.Order.status.in_(["NEW", "PARTIALLY_EXECUTED"]),
            schemas.Order.price.isnot(None),
        )

        if not is_market_order:
            if new_order.direction == "BUY":
                base_query = base_query.filter(
                    schemas.Order.price <= new_order.price
                )
            else:
                base_query = base_query.filter(
                    schemas.Order.price >= new_order.price
                )

        matching_orders = (
            base_query.order_by(
                (
                    schemas.Order.price.asc()
                    if new_order.direction == "BUY"
                    else schemas.Order.price.desc()
                ),
                schemas.Order.created_at.asc(),
            )
            .with_for_update()
            .all()
        )

        qty_to_fill = new_order.quantity - new_order.filled
        trades = []

        for counter_order in matching_orders:
            if qty_to_fill <= 0:
                break

            available_qty = counter_order.quantity - counter_order.filled
            trade_qty = min(qty_to_fill, available_qty)

            if trade_qty <= 0:
                continue

            trade_price = counter_order.price

            if new_order.direction == "BUY":
                buyer_rub_balance = get_balance(db, new_order.user_id, "RUB")
                seller_ticker_balance = get_balance(
                    db, counter_order.user_id, new_order.instrument_ticker
                )

                required_rub = trade_qty * trade_price

                if not buyer_rub_balance or buyer_rub_balance.amount < required_rub:
                    continue

                if (
                    not seller_ticker_balance
                    or seller_ticker_balance.amount < trade_qty
                ):
                    continue
            else:
                seller_ticker_balance = get_balance(
                    db, new_order.user_id, new_order.instrument_ticker
                )
                buyer_rub_balance = get_balance(db, counter_order.user_id, "RUB")

                required_rub = trade_qty * trade_price

                if (
                    not seller_ticker_balance
                    or seller_ticker_balance.amount < trade_qty
                ):
                    continue

                if not buyer_rub_balance or buyer_rub_balance.amount < required_rub:
                    continue

            trade = schemas.Transaction(
                instrument_ticker=new_order.instrument_ticker,
                price=trade_price,
                quantity=trade_qty,
                buyer_id=(
                    new_order.user_id
                    if new_order.direction == "BUY"
                    else counter_order.user_id
                ),
                seller_id=(
                    counter_order.user_id
                    if new_order.direction == "BUY"
                    else new_order.user_id
                ),
                created_at=datetime.utcnow(),
            )
            db.add(trade)
            trades.append(trade)

            new_order.filled += trade_qty
            counter_order.filled += trade_qty

            new_order.status = (
                "EXECUTED"
                if new_order.filled == new_order.quantity
                else "PARTIALLY_EXECUTED" if new_order.filled > 0 else "NEW"
            )
            counter_order.status = (
                "EXECUTED"
                if counter_order.filled == counter_order.quantity
                else "PARTIALLY_EXECUTED"
            )

            db.add(new_order)
            db.add(counter_order)
            qty_to_fill -= trade_qty

    for trade in trades:
        try:
            if new_order.direction == "BUY":
                update_balance(
                    db, trade.buyer_id, new_order.instrument_ticker, trade.quantity
                )
                update_balance(
                    db, trade.buyer_id, "RUB", -trade.quantity * trade.price
                )
                update_balance(
                    db, trade.seller_id, "RUB", trade.quantity * trade.price
                )
                update_balance(
                    db,
                    trade.seller_id,
                    new_order.instrument_ticker,
                    -trade.quantity,
                )
            else:
                update_balance(
                    db, trade.seller_id, "RUB", trade.quantity * trade.price
                )
                update_balance(
                    db,
                    trade.seller_id,
                    new_order.instrument_ticker,
                    -trade.quantity,
                )
                update_balance(
                    db, trade.buyer_id, new_order.instrument_ticker, trade.quantity
                )
                update_balance(
                    db, trade.buyer_id, "RUB", -trade.quantity * trade.price
                )
        except ValueError:
            db.rollback()
            raise

    db.commit()
    db.refresh(new_order)
    return new_order