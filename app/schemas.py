from __future__ import annotations

from pydantic import BaseModel, field_validator


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
