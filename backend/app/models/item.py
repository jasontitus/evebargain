from sqlalchemy import Integer, String, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ItemCategory(Base):
    __tablename__ = "item_categories"

    category_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class ItemType(Base):
    __tablename__ = "item_types"

    type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    group_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    category_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    market_group_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    # Cubic metres per unit, packaged. ESI reports both an assembled `volume`
    # and a `packaged_volume`; market goods are packaged, and for ships the two
    # differ by an order of magnitude (a Rifter is 27,289 m3 assembled against
    # 2,500 packaged), so using the wrong one would misprice every hauling
    # decision. Nullable because it backfills after the catalogue load.
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
