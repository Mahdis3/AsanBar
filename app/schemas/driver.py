from uuid import UUID
from typing import Optional
from pydantic import BaseModel


class DriverLocationUpdate(BaseModel):
    lat: float
    lng: float


class DriverProfileResponse(BaseModel):
    id: UUID
    user_id: UUID
    vehicle_plate: str
    vehicle_type: str
    status: str
    rating: float
    total_deliveries: float
    is_verified: bool

    model_config = {"from_attributes": True}


class NearbyDriverResponse(BaseModel):
    driver_id: str
    distance_km: float


class DriverRegisterRequest(BaseModel):
    vehicle_plate: str
    vehicle_type: str  # van | truck | motorcycle
