from datetime import datetime

from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    character_name: Mapped[str] = mapped_column(String(255), nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    current_region_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_system_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    config: Mapped["UserConfig"] = relationship(back_populates="user", uselist=False)


class UserConfig(Base):
    __tablename__ = "user_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), unique=True, nullable=False
    )
    discount_threshold: Mapped[float] = mapped_column(Float, default=0.10)
    tracked_category_ids: Mapped[str] = mapped_column(
        Text, default="[6,8,4,91]"
    )  # JSON array
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sound_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_volume: Mapped[int] = mapped_column(Integer, default=5)
    min_profit_isk: Mapped[float] = mapped_column(Float, default=1000000.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="config")
