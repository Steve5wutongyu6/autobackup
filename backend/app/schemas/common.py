"""Shared response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApiMessage(BaseModel):
    """
    Standard lightweight message envelope.

    Attributes:
        message: Human-readable operation result.
    """

    message: str


class TimestampedModel(BaseModel):
    """
    Base schema carrying ORM compatibility and timestamps.

    Attributes:
        created_at: UTC creation time.
        updated_at: UTC update time when available.
    """

    model_config = ConfigDict(from_attributes=True)

    created_at: datetime
    updated_at: datetime | None = None

