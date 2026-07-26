"""The item catalogue: every tradeable thing, and what category it belongs to.

WHY THIS TABLE IS LOAD-BEARING
    Market data from ESI identifies items only by a numeric `type_id`. This
    table is what turns 34 into "Tritanium", and what makes "only show me
    ships and ammo" possible at all.

    The price comparison joins against it, and an *inner* join drops any row
    with no match -- so an empty catalogue silently produces zero deals at
    every threshold, looking exactly like a quiet market. That is why the app
    now loads it automatically at startup (see main.py) and logs loudly when
    it is empty.
"""

from sqlalchemy import Integer, String, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ItemCategory(Base):
    """A broad grouping such as Ships, Modules or Drones."""

    __tablename__ = "item_categories"

    category_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class ItemType(Base):
    """A single tradeable item.

    Note the primary key is EVE's own `type_id` rather than a generated number
    -- these ids come from the game and are already stable and unique, so
    inventing a second identifier would only add a lookup.
    """

    __tablename__ = "item_types"

    type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    group_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    category_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # Present only for things actually sold on the market. Items without one
    # (test articles, unused assets) are filtered out when building the list of
    # types to track.
    market_group_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # CCP marks removed or never-released items unpublished; they can still
    # appear in group listings, so this filters them out.
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    # Cubic metres per unit, packaged. ESI reports both an assembled `volume`
    # and a `packaged_volume`; market goods are packaged, and for ships the two
    # differ by an order of magnitude (a Rifter is 27,289 m3 assembled against
    # 2,500 packaged), so using the wrong one would misprice every hauling
    # decision. Nullable because it backfills after the catalogue load.
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
