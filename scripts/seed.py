"""
اجرا: python scripts/seed.py
داده اولیه برای تست: ادمین، شرکت، راننده، مشتری
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db.session import AsyncSessionLocal, engine, Base
from app.models.user import User, UserRole
from app.models.driver import Driver, DriverStatus
from app.core.security import hash_password


SEED_USERS = [
    {
        "email": "admin@asanbar.ir",
        "phone": "09100000001",
        "full_name": "مدیر سیستم",
        "password": "Admin@1234",
        "role": UserRole.ADMIN,
    },
    {
        "email": "company@asanbar.ir",
        "phone": "09100000002",
        "full_name": "شرکت حمل‌ونقل البرز",
        "password": "Company@1234",
        "role": UserRole.COMPANY,
    },
    {
        "email": "driver1@asanbar.ir",
        "phone": "09100000003",
        "full_name": "علی رضایی",
        "password": "Driver@1234",
        "role": UserRole.DRIVER,
    },
    {
        "email": "driver2@asanbar.ir",
        "phone": "09100000004",
        "full_name": "محمد کریمی",
        "password": "Driver@1234",
        "role": UserRole.DRIVER,
    },
    {
        "email": "customer@asanbar.ir",
        "phone": "09100000005",
        "full_name": "سارا احمدی",
        "password": "Customer@1234",
        "role": UserRole.CUSTOMER,
    },
]


async def seed():
    print("🌱 شروع seed...")

    async with AsyncSessionLocal() as db:
        for u_data in SEED_USERS:
            from sqlalchemy import select
            existing = await db.execute(select(User).where(User.email == u_data["email"]))
            if existing.scalar_one_or_none():
                print(f"  ⏩ کاربر موجود: {u_data['email']}")
                continue

            user = User(
                email=u_data["email"],
                phone=u_data["phone"],
                full_name=u_data["full_name"],
                hashed_password=hash_password(u_data["password"]),
                role=u_data["role"],
            )
            db.add(user)
            await db.flush()

            # پروفایل راننده
            if u_data["role"] == UserRole.DRIVER:
                plate = "11-AAA-111" if "driver1" in u_data["email"] else "22-BBB-222"
                driver = Driver(
                    user_id=user.id,
                    vehicle_plate=plate,
                    vehicle_type="van",
                    status=DriverStatus.AVAILABLE,
                    is_verified=True,
                )
                db.add(driver)
                print(f"  ✅ راننده: {u_data['full_name']} ({plate})")
            else:
                print(f"  ✅ کاربر: {u_data['full_name']} ({u_data['role'].value})")

        await db.commit()

    print("\n✅ Seed کامل شد!")
    print("\n📋 اطلاعات ورود:")
    print("  Admin:    admin@asanbar.ir    / Admin@1234")
    print("  Company:  company@asanbar.ir  / Company@1234")
    print("  Driver 1: driver1@asanbar.ir  / Driver@1234")
    print("  Driver 2: driver2@asanbar.ir  / Driver@1234")
    print("  Customer: customer@asanbar.ir / Customer@1234")


if __name__ == "__main__":
    asyncio.run(seed())
