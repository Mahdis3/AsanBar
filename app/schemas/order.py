from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator


class LocationSchema(BaseModel):
    lat: float
    lng: float
    address: str

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, v: float) -> float:
        if not -90 <= v <= 90:
            raise ValueError("Latitude must be between -90 and 90")
        return v

    @field_validator("lng")
    @classmethod
    def validate_lng(cls, v: float) -> float:
        if not -180 <= v <= 180:
            raise ValueError("Longitude must be between -180 and 180")
        return v


class OrderCreateRequest(BaseModel):
    pickup_location: LocationSchema
    dropoff_location: LocationSchema
    cargo_description: str
    cargo_weight_kg: Optional[float] = None
    special_instructions: Optional[str] = None


class OrderResponse(BaseModel):
    id: UUID
    customer_id: UUID
    assigned_driver_id: Optional[UUID]
    pickup_location: dict
    dropoff_location: dict
    cargo_description: str
    cargo_weight_kg: Optional[float]
    special_instructions: Optional[str]
    status: str
    price: Optional[float]
    created_at: datetime
    assigned_at: Optional[datetime]
    picked_up_at: Optional[datetime]
    delivered_at: Optional[datetime]

    model_config = {"from_attributes": True}


class OrderStatusUpdateRequest(BaseModel):
    status: str  # picked_up | delivered | cancelled
