import enum
import uuid
from sqlalchemy import (
    Column,
    String,
    Float,
    DateTime,
    Enum,
    ForeignKey,
    Text,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.session import Base


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    PICKED_UP = "picked_up"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    assigned_driver_id = Column(
        UUID(as_uuid=True), ForeignKey("drivers.id"), nullable=True
    )

    # مکان‌ها به صورت JSONB: {"lat": 35.7, "lng": 51.4, "address": "..."}
    pickup_location = Column(JSONB, nullable=False)
    dropoff_location = Column(JSONB, nullable=False)

    # اطلاعات بار
    cargo_description = Column(String(500), nullable=False)
    cargo_weight_kg = Column(Float, nullable=True)
    special_instructions = Column(Text, nullable=True)

    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING, nullable=False)
    price = Column(Float, nullable=True)  # قیمت نهایی

    # زمان‌ها
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    picked_up_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    customer = relationship("User", back_populates="orders", foreign_keys=[customer_id])
    driver = relationship(
        "Driver", back_populates="assigned_orders", foreign_keys=[assigned_driver_id]
    )

    # ایندکس برای سفارش‌های pending — کوئری مکرر در AssignmentService
    __table_args__ = (
        Index("idx_orders_status_created", "status", "created_at"),
        Index("idx_orders_customer", "customer_id"),
        Index("idx_orders_driver", "assigned_driver_id"),
    )

    def __repr__(self) -> str:
        return f"<Order {self.id} ({self.status})>"
