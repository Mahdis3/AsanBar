import enum
import uuid
from sqlalchemy import Column, String, Float, Boolean, DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.session import Base


class DriverStatus(str, enum.Enum):
    OFFLINE = "offline"
    AVAILABLE = "available"
    BUSY = "busy"


class Driver(Base):
    __tablename__ = "drivers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    vehicle_plate = Column(String(20), unique=True, nullable=False)
    vehicle_type = Column(String(50), nullable=False)  # van, truck, motorcycle
    status = Column(Enum(DriverStatus), default=DriverStatus.OFFLINE, nullable=False)
    rating = Column(Float, default=5.0)
    total_deliveries = Column(Float, default=0)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="driver_profile")
    assigned_orders = relationship("Order", back_populates="driver", foreign_keys="Order.assigned_driver_id")

    def __repr__(self) -> str:
        return f"<Driver {self.vehicle_plate} ({self.status})>"
