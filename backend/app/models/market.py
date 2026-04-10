from datetime import datetime

from sqlalchemy import Integer, Float, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MarketCache(Base):
    __tablename__ = "market_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    type_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    lowest_sell: Mapped[float | None] = mapped_column(Float, nullable=True)
    highest_buy: Mapped[float | None] = mapped_column(Float, nullable=True)
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    volume_remain: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("region_id", "type_id", name="uq_region_type"),
    )
