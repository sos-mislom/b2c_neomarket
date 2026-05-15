from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class AddCartItemRequest(BaseModel):
    sku_id: str
    quantity: int = Field(ge=1)


class UpdateCartItemRequest(BaseModel):
    quantity: int = Field(ge=1)


class SubscribeRequest(BaseModel):
    notify_on: list[str]

    @field_validator("notify_on")
    @classmethod
    def validate_notify_on(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("notify_on must not be empty")
        allowed = {"IN_STOCK", "PRICE_DOWN"}
        normalized = []
        for item in value:
            upper_item = item.upper()
            if upper_item not in allowed:
                raise ValueError("notify_on contains unsupported value")
            if upper_item not in normalized:
                normalized.append(upper_item)
        return normalized


class BannerEventIn(BaseModel):
    banner_id: str
    event: str
    timestamp: datetime

    @field_validator("event")
    @classmethod
    def validate_event(cls, value: str) -> str:
        if value not in {"impression", "click"}:
            raise ValueError("event must be impression or click")
        return value


class BannerEventsRequest(BaseModel):
    events: list[BannerEventIn]

    @field_validator("events")
    @classmethod
    def validate_events(cls, value: list[BannerEventIn]) -> list[BannerEventIn]:
        if not value:
            raise ValueError("events must not be empty")
        if len(value) > 50:
            raise ValueError("events must contain at most 50 items")
        return value


class CheckoutRequest(BaseModel):
    idempotency_key: str | None = None
    comment: str | None = None
    delivery_address: str | None = None


class CancelOrderRequest(BaseModel):
    reason: str | None = None


class ProductEventRequest(BaseModel):
    type: str
    sku_ids: list[str]
    idempotency_key: str

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("idempotency_key must not be empty")
        return value
